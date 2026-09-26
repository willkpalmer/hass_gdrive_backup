import asyncio
from typing import Any, Callable, Dict, List, Optional

from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType
from injector import inject, singleton

from ..config import Config, Startable
from ..exceptions import KnownError
from ..logger import getLogger
from .harequests import HaRequests

logger = getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 20
CALL_TIMEOUT_SECONDS = 60
RECONNECT_MIN_SECONDS = 10
RECONNECT_MAX_SECONDS = 300

ERROR_HA_WEBSOCKET = "home_assistant_websocket"


class HomeAssistantWebsocketError(KnownError):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail

    def message(self):
        return "Couldn't use Home Assistant's backup API: " + self.detail

    def code(self):
        return ERROR_HA_WEBSOCKET


@singleton
class HaWebsocket(Startable):
    """
    A connection to Home Assistant Core's websocket API, made through the Supervisor's proxy at
    /core/websocket and authenticated with the add-on's Supervisor token.

    Calls connect on demand. Once started, it also keeps the connection open in the background so
    it can deliver Home Assistant's backup events to listeners.
    """
    @inject
    def __init__(self, config: Config, session: ClientSession, harequests: HaRequests):
        self._config = config
        self._session = session
        self._harequests = harequests
        self._ws: Optional[ClientWebSocketResponse] = None
        self._reader: Optional[asyncio.Task] = None
        self._runner: Optional[asyncio.Task] = None
        self._connect_lock = asyncio.Lock()
        self._next_id = 1
        self._pending: Dict[int, asyncio.Future] = {}
        self._backup_event_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._events_id: Optional[int] = None
        self._stopped = False

    def onBackupEvent(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a listener for Home Assistant's backup manager events (from backup/subscribe_events)."""
        self._backup_event_listeners.append(listener)

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def call(self, message_type: str, **data) -> Any:
        """Sends a command and returns its result, raising HomeAssistantWebsocketError if it fails."""
        await self._ensureConnected()
        return await self._send(message_type, data)

    async def start(self):
        self._stopped = False
        self._runner = asyncio.create_task(self._keepConnected(), name="Home Assistant websocket")

    async def stop(self):
        self._stopped = True
        for task in [self._runner, self._reader]:
            if task is not None and not task.done():
                task.cancel()
        if self._ws is not None:
            await self._ws.close()
        self._ws = None

    async def _keepConnected(self):
        delay = RECONNECT_MIN_SECONDS
        while not self._stopped:
            try:
                await self._ensureConnected()
                delay = RECONNECT_MIN_SECONDS
                await asyncio.shield(self._reader)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("Home Assistant websocket unavailable: %s", e)
            if self._stopped:
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_SECONDS)

    async def _ensureConnected(self):
        if self.connected:
            return
        async with self._connect_lock:
            if self.connected:
                return
            try:
                await asyncio.wait_for(self._connect(), CONNECT_TIMEOUT_SECONDS)
            except HomeAssistantWebsocketError:
                raise
            except Exception as e:
                raise HomeAssistantWebsocketError("unable to connect ({0})".format(e or type(e).__name__))

    async def _connect(self):
        url = self._harequests.getSupervisorURL().with_path("/core/websocket")
        ws = await self._session.ws_connect(url, heartbeat=55)
        try:
            message = await ws.receive_json()
            if message.get("type") != "auth_required":
                raise HomeAssistantWebsocketError("unexpected greeting " + str(message.get("type")))
            await ws.send_json({"type": "auth", "access_token": self._harequests._getToken()})
            message = await ws.receive_json()
            if message.get("type") != "auth_ok":
                raise HomeAssistantWebsocketError("authentication failed")
        except Exception:
            await ws.close()
            raise
        self._ws = ws
        self._reader = asyncio.create_task(self._read(ws), name="Home Assistant websocket reader")
        try:
            self._events_id = self._reserveId()
            await self._send("backup/subscribe_events", {}, message_id=self._events_id)
        except HomeAssistantWebsocketError as e:
            # Older Home Assistant versions don't have backup events, which is fine.
            logger.debug("Couldn't subscribe to Home Assistant backup events: %s", e.detail)
            self._events_id = None

    def _reserveId(self) -> int:
        message_id = self._next_id
        self._next_id += 1
        return message_id

    async def _send(self, message_type: str, data: Dict[str, Any], message_id: Optional[int] = None) -> Any:
        ws = self._ws
        if ws is None or ws.closed:
            raise HomeAssistantWebsocketError("not connected")
        if message_id is None:
            message_id = self._reserveId()
        future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        try:
            await ws.send_json({"id": message_id, "type": message_type, **data})
            return await asyncio.wait_for(future, CALL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            raise HomeAssistantWebsocketError("'{0}' timed out".format(message_type))
        finally:
            self._pending.pop(message_id, None)

    async def _read(self, ws: ClientWebSocketResponse):
        try:
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    continue
                self._dispatch(message.json())
        finally:
            error = HomeAssistantWebsocketError("connection closed")
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()
            if self._ws is ws:
                self._ws = None

    def _dispatch(self, message: Dict[str, Any]):
        if message.get("type") == "result":
            future = self._pending.get(message.get("id"))
            if future is None or future.done():
                return
            if message.get("success"):
                future.set_result(message.get("result"))
            else:
                error = message.get("error") or {}
                future.set_exception(HomeAssistantWebsocketError(
                    "{0} ({1})".format(error.get("message", "request failed"), error.get("code", "unknown"))))
        elif message.get("type") == "event" and message.get("id") == self._events_id:
            event = message.get("event") or {}
            for listener in self._backup_event_listeners:
                try:
                    listener(event)
                except Exception as e:
                    logger.error("Error handling a Home Assistant backup event")
                    logger.printException(e)

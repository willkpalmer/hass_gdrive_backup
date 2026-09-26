import asyncio
from datetime import timedelta
from typing import Dict, Optional, Tuple

from injector import inject, singleton

from ..config import Config, Setting, Startable
from ..logger import FORWARD, getLogger
from ..time import Time
from .harequests import HaRequests

logger = getLogger(__name__)

FORWARD_INTERVAL_SECONDS = 5
# The same message from the same place is only forwarded once in this long, so a repeating
# problem can't flood Home Assistant's log.
REPEAT_INTERVAL = timedelta(minutes=15)
MAX_MESSAGE_LENGTH = 4000
LEVELS = {"WARNING": "warning", "ERROR": "error", "CRITICAL": "critical"}


@singleton
class HaLogForwarder(Startable):
    """
    Copies the app's warnings and errors into Home Assistant's own log (home-assistant.log and
    Settings > System > Logs) using the system_log.write service, under the app's logger names
    (hass_gdrive_backup.*). Log tools that read Home Assistant's log can then find them without
    also reading the add-on's log.
    """
    @inject
    def __init__(self, config: Config, harequests: HaRequests, time: Time):
        self._config = config
        self._harequests = harequests
        self._time = time
        self._last_sent: Dict[Tuple[str, str], object] = {}
        self._task: Optional[asyncio.Task] = None
        config.subscribe(self._updateEnabled)

    def _updateEnabled(self):
        FORWARD.enabled = self._config.get(Setting.LOG_TO_HOME_ASSISTANT)
        if not FORWARD.enabled:
            FORWARD.pending.clear()

    async def start(self):
        self._updateEnabled()
        self._task = asyncio.create_task(self._run(), name="Home Assistant log forwarder")

    async def stop(self):
        FORWARD.enabled = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.wait([self._task])

    async def _run(self):
        while True:
            await asyncio.sleep(FORWARD_INTERVAL_SECONDS)
            await self.flush()

    async def flush(self) -> None:
        """Sends every queued warning and error to Home Assistant."""
        while len(FORWARD.pending) > 0:
            record = FORWARD.pending[0]
            message = record.getMessage().strip()
            key = (record.name, message.split("\n", 1)[0])
            now = self._time.now()
            last = self._last_sent.get(key)
            if last is not None and now - last < REPEAT_INTERVAL:
                FORWARD.pending.popleft()
                continue
            try:
                await self._harequests.systemLogWrite(
                    message[:MAX_MESSAGE_LENGTH], LEVELS.get(record.levelname, "error"), record.name)
            except Exception as e:
                # Home Assistant might be restarting. Keep the record and try again later. This is logged
                # at debug level, which isn't forwarded, so it can't loop.
                logger.debug("Couldn't write to Home Assistant's log: %s", e)
                return
            FORWARD.pending.popleft()
            self._last_sent[key] = now

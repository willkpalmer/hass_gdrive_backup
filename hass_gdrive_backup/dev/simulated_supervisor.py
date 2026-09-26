import asyncio
from asyncio.tasks import sleep
from datetime import timedelta
import random
import string
import io

from backup.config import Config, Version
from backup.time import Time
from aiohttp import WSMsgType
from aiohttp.web import (HTTPBadRequest, HTTPNotFound,
                         HTTPUnauthorized, Request, Response, get,
                         json_response, post, delete, FileResponse, WebSocketResponse)
from injector import inject, singleton
from .base_server import BaseServer
from .ports import Ports
from typing import Any, Dict
from tests.helpers import all_addons, createBackupTar, parseBackupInfo

URL_MATCH_BACKUP_FULL = "^/backups/new/full$"
URL_MATCH_BACKUP_DELETE = "^/backups/.*$"
URL_MATCH_BACKUP_DOWNLOAD = "^/backups/.*/download$"
URL_MATCH_MISC_INFO = "^/info$"
URL_MATCH_CORE_API = "^/core/api.*$"
URL_MATCH_START_ADDON = "^/addons/.*/start$"
URL_MATCH_STOP_ADDON = "^/addons/.*/stop$"
URL_MATCH_ADDON_INFO = "^/addons/.*/info$"
URL_MATCH_SELF_OPTIONS = "^/addons/self/options$"

URL_MATCH_SNAPSHOT = "^/snapshots.*$"
URL_MATCH_BACKUPS = "^/backups.*$"
URL_MATCH_MOUNT = "^/mounts*$"


@singleton
class SimulatedSupervisor(BaseServer):
    @inject
    def __init__(self, config: Config, ports: Ports, time: Time):
        self._config = config
        self._time = time
        self._ports = ports
        self._auth_token = "test_header"
        self._backups: Dict[str, Any] = {}
        self._backup_data: Dict[str, bytearray] = {}
        self._backup_lock = asyncio.Lock()
        self._backup_inner_lock = asyncio.Lock()
        self._entities = {}
        self._events = []
        self._attributes = {}
        self._notification = None
        self._min_backup_size = 1024 * 1024 * 5
        self._max_backup_size = 1024 * 1024 * 5
        self._addon_slug = "self_slug"
        self._options = self.defaultOptions()
        self._username = "user"
        self._password = "pass"
        self._addons = all_addons.copy()
        self._super_version = Version(2023, 7)
        self._mounts = {
            'default_backup_mount': None,
            'mounts': [
                {
                    "name": "my_media_share",
                    "usage": "media",
                    "type": "cifs",
                    "server": "server.local",
                    "share": "media",
                    "state": "active"
                },
                {
                    "name": "my_backup_share",
                    "usage": "backup",
                    "type": "nfs",
                    "server": "server.local",
                    "share": "media",
                    "state": "active"
                }
            ]
        }

        # Simulates Home Assistant Core's backup websocket API (proxied by the supervisor at /core/websocket)
        self._mqtt_service = None
        self._backup_passwords = {}
        self._restores = []
        self._notify_services = {"mobile_app_phone"}
        self._notify_calls = []
        self._system_log = []
        self._core_websocket_available = True
        self._core_event_subscribers = []
        self._core_websockets = set()
        self._core_backup_config = {
            "agents": {},
            "automatic_backups_configured": False,
            "create_backup": {
                "agent_ids": ["hassio.local"],
                "include_addons": None,
                "include_all_addons": True,
                "include_database": True,
                "include_folders": None,
                "name": None,
                "password": None,
            },
            "last_attempted_automatic_backup": None,
            "last_completed_automatic_backup": None,
            "next_automatic_backup": None,
            "next_automatic_backup_additional": False,
            "retention": {"copies": 3, "days": None},
            "schedule": {"days": [], "recurrence": "never", "time": None},
        }

        self.installAddon(self._addon_slug, "GDrive Backup Utility")
        self.installAddon("42", "The answer")
        self.installAddon("sgadg", "sdgsagsdgsggsd")

    def defaultOptions(self):
        return {
            "max_backups_in_ha": 4,
            "max_backups_in_google_drive": 4,
            "days_between_backups": 3
        }

    def routes(self):
        return [
            post('/addons/{slug}/options', self._updateOptions),
            post("/core/api/services/persistent_notification/dismiss", self._dismissNotification),
            post("/core/api/services/persistent_notification/create", self._createNotification),
            post("/core/api/services/notify/{name}", self._notifyService),
            post("/core/api/services/system_log/write", self._systemLogWrite),
            post("/core/api/events/{name}", self._haEventUpdate),
            post("/core/api/states/{entity}", self._haStateUpdate),
            delete("/core/api/states/{entity}", self._haStateDelete),
            get('/services/mqtt', self._mqttService),
            post('/auth', self._authenticate),
            get('/auth', self._authenticate),
            get('/info', self._miscInfo),
            get('/addons/self/info', self._selfInfo),
            get('/addons', self._allAddons),
            get('/addons/{slug}/info', self._addonInfo),

            post('/addons/{slug}/start', self._startAddon),
            post('/addons/{slug}/stop', self._stopAddon),
            get('/addons/{slug}/logo', self._logoAddon),
            get('/addons/{slug}/icon', self._logoAddon),

            get('/core/info', self._coreInfo),
            get('/core/websocket', self._coreWebsocket),
            get('/supervisor/info', self._supervisorInfo),
            get('/supervisor/logs', self._supervisorLogs),
            get('/core/logs', self._coreLogs),
            get('/debug/insert/backup', self._debug_insert_backup),
            get('/debug/info', self._debugInfo),
            post("/debug/mounts", self._setMounts),

            get('/backups', self._getBackups),
            get('/mounts', self._getMounts),
            delete('/backups/{slug}', self._deletebackup),
            post('/backups/new/upload', self._uploadbackup),
            post('/backups/new/partial', self._newbackup),
            post('/backups/new/full', self._newbackup),
            get('/backups/new/full', self._newbackup),
            get('/backups/{slug}/download', self._backupDownload),
            get('/backups/{slug}/info', self._backupDetail),
            post('/backups/{slug}/restore/full', self._restoreBackup),
            post('/backups/{slug}/restore/partial', self._restoreBackup),
            get('/debug/backups/lock', self._lock_backups),

            # TODO: remove once the api path is fully deprecated
            get('/snapshots', self._getSnapshots),
            post('/snapshots/{slug}/remove', self._deletebackup),
            post('/snapshots/new/upload', self._uploadbackup),
            post('/snapshots/new/partial', self._newbackup),
            post('/snapshots/new/full', self._newbackup),
            get('/snapshots/new/full', self._newbackup),
            get('/snapshots/{slug}/download', self._backupDownload),
            get('/snapshots/{slug}/info', self._backupDetail),
        ]

    def getEvents(self):
        return self._events.copy()

    def getEntity(self, entity):
        return self._entities.get(entity)

    def clearEntities(self):
        self._entities = {}

    def addon(self, slug):
        for addon in self._addons:
            if addon["slug"] == slug:
                return addon
        return None

    def getAttributes(self, attribute):
        return self._attributes.get(attribute)

    def getNotification(self):
        return self._notification

    def _formatErrorResponse(self, error: str) -> str:
        return json_response({'result': error})

    def _formatDataResponse(self, data: Any) -> Response:
        return json_response({'result': 'ok', 'data': data})

    async def toggleBlockBackup(self):
        if self._backup_lock.locked():
            self._backup_lock.release()
        else:
            await self._backup_lock.acquire()

    async def _verifyHeader(self, request) -> bool:
        if request.headers.get("Authorization", None) == "Bearer " + self._auth_token:
            return
        if request.headers.get("X-Supervisor-Token", None) == self._auth_token:
            return
        raise HTTPUnauthorized()

    async def _getSnapshots(self, request: Request):
        await self._verifyHeader(request)
        return self._formatDataResponse({'snapshots': list(self._backups.values())})

    async def _getBackups(self, request: Request):
        await self._verifyHeader(request)
        return self._formatDataResponse({'backups': list(self._backups.values())})

    async def _getMounts(self, request: Request):
        await self._verifyHeader(request)
        return self._formatDataResponse(self._mounts)
    
    async def _setMounts(self, request: Request):
        self._mounts = await request.json()
        return self._formatDataResponse({})

    async def _stopAddon(self, request: Request):
        await self._verifyHeader(request)
        slug = request.match_info.get('slug')
        for addon in self._addons:
            if addon.get("slug", "") == slug:
                if addon.get("state") == "started":
                    addon["state"] = "stopped"
                    return self._formatDataResponse({})
        raise HTTPBadRequest()

    async def _logoAddon(self, request: Request):
        await self._verifyHeader(request)
        return FileResponse('hass_gdrive_backup/backup/static/images/logo.png')

    async def _startAddon(self, request: Request):
        await self._verifyHeader(request)
        slug = request.match_info.get('slug')
        for addon in self._addons:
            if addon.get("slug", "") == slug:
                if addon.get("state") != "started":
                    addon["state"] = "started"
                    return self._formatDataResponse({})
        raise HTTPBadRequest()

    async def _addonInfo(self, request: Request):
        await self._verifyHeader(request)
        slug = request.match_info.get('slug')
        for addon in self._addons:
            if addon.get("slug", "") == slug:
                return self._formatDataResponse({
                    'boot': addon.get("boot"),
                    'watchdog': addon.get("watchdog"),
                    'state': addon.get("state"),
                })
        raise HTTPBadRequest()

    async def _supervisorInfo(self, request: Request):
        await self._verifyHeader(request)
        return self._formatDataResponse(
            {
                'version': str(self._super_version)
            }
        )

    async def _allAddons(self, request: Request):
        await self._verifyHeader(request)
        return self._formatDataResponse(
            {
                "addons": list(self._addons).copy()
            }
        )

    async def _supervisorLogs(self, request: Request):
        await self._verifyHeader(request)
        return Response(body=self.generate_random_text(20, 10, 20))

    def generate_random_text(self, line_count, min_words=5, max_words=10):
        lines = []
        log_levels = ["WARN", "WARNING", "INFO", "ERROR", "DEBUG"]
        for _ in range(line_count):
            level = random.choice(log_levels)
            word_count = random.randint(min_words, max_words)
            words = [random.choice(string.ascii_lowercase) for _ in range(word_count)]
            line = level + " " + ' '.join(''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(3, 10))) for _ in words)
            lines.append(line)
        return '\n'.join(lines)

    async def _coreLogs(self, request: Request):
        await self._verifyHeader(request)
        return Response(body="Core Log line 1\nCore Log Line 2")

    async def _coreInfo(self, request: Request):
        await self._verifyHeader(request)
        return self._formatDataResponse(
            {
                "version": "1.3.3.7",
                "last_version": "1.3.3.8",
                "machine": "VS Dev",
                "ip_address": "127.0.0.1",
                "arch": "x86",
                "image": "image",
                "custom": "false",
                "boot": "true",
                "port": self._ports.server,
                "ssl": "false",
                "watchdog": "what is this",
                "wait_boot": "so many arguments"
            }
        )

    async def _internalNewBackup(self, request: Request, input_json, date=None, verify_header=True) -> str:
        async with self._backup_lock:
            async with self._backup_inner_lock:
                if 'wait' in input_json:
                    await sleep(input_json['wait'])
                if verify_header:
                    await self._verifyHeader(request)
                slug = self.generateId(8)
                password = input_json.get('password', None)
                data = createBackupTar(
                    slug,
                    input_json.get('name', "Default name"),
                    date=date or self._time.now(),
                    padSize=int(random.uniform(self._min_backup_size, self._max_backup_size)),
                    included_folders=input_json.get('folders', None),
                    included_addons=input_json.get('addons', None),
                    password=password)
                backup_info = parseBackupInfo(data)
                backup_info['extra'] = input_json.get('extra')
                self._backup_passwords[slug] = password
                self._backups[slug] = backup_info
                self._backup_data[slug] = bytearray(data.getbuffer())
                return slug

    def setCoreWebsocketAvailable(self, available: bool):
        self._core_websocket_available = available

    def setCoreBackupConfig(self, **changes):
        """Changes the simulated Home Assistant backup config, e.g. schedule={"recurrence": "daily"}"""
        for key, value in changes.items():
            if isinstance(value, dict) and isinstance(self._core_backup_config.get(key), dict):
                self._core_backup_config[key].update(value)
            else:
                self._core_backup_config[key] = value

    async def createAutomaticBackup(self, date=None):
        """Creates a backup the way Home Assistant's automatic backups do."""
        slug = await self._internalNewBackup(None, {
            "name": self._core_backup_config["create_backup"]["name"] or "Automatic backup",
            "password": self._core_backup_config["create_backup"]["password"],
            "extra": {"instance_id": "simulated", "with_automatic_settings": True},
        }, date=date, verify_header=False)
        self._core_backup_config["last_completed_automatic_backup"] = (date or self._time.now()).isoformat()
        return slug

    async def _coreWebsocket(self, request: Request):
        if not self._core_websocket_available:
            raise HTTPNotFound()
        ws = WebSocketResponse()
        await ws.prepare(request)
        self._core_websockets.add(ws)
        await ws.send_json({"type": "auth_required", "ha_version": "2026.10.0"})
        auth = await ws.receive_json()
        if auth.get("type") != "auth" or auth.get("access_token") != self._auth_token:
            await ws.send_json({"type": "auth_invalid", "message": "Invalid access token"})
            await ws.close()
            return ws
        await ws.send_json({"type": "auth_ok", "ha_version": "2026.10.0"})
        try:
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    continue
                await self._handleCoreCommand(ws, message.json())
        finally:
            self._core_event_subscribers = [s for s in self._core_event_subscribers if s[0] is not ws]
            self._core_websockets.discard(ws)
        return ws

    async def closeWebsockets(self):
        for ws in list(self._core_websockets):
            await ws.close()

    async def _handleCoreCommand(self, ws: WebSocketResponse, command):
        command_type = command.get("type")
        if command_type == "backup/config/info":
            await self._coreResult(ws, command, {"config": dict(self._core_backup_config)})
        elif command_type == "backup/subscribe_events":
            self._core_event_subscribers.append((ws, command["id"]))
            await ws.send_json({"id": command["id"], "type": "event", "event": {"manager_state": "idle"}})
            await self._coreResult(ws, command, None)
        elif command_type == "backup/generate_with_automatic_settings":
            await self._coreEvent({"manager_state": "create_backup", "stage": None, "state": "in_progress", "reason": None})
            await self.createAutomaticBackup()
            await self._coreResult(ws, command, {"backup_job_id": self.generateId(8)})
            await self._coreEvent({"manager_state": "create_backup", "stage": None, "state": "completed", "reason": None})
        else:
            await ws.send_json({"id": command.get("id"), "type": "result", "success": False,
                                "error": {"code": "unknown_command", "message": "Unknown command."}})

    async def _coreResult(self, ws, command, result):
        await ws.send_json({"id": command["id"], "type": "result", "success": True, "result": result})

    async def _coreEvent(self, event):
        for ws, subscription_id in list(self._core_event_subscribers):
            if not ws.closed:
                await ws.send_json({"id": subscription_id, "type": "event", "event": event})

    async def createBackup(self, input_json, date=None):
        return await self._internalNewBackup(None, input_json, date=date, verify_header=False)

    async def _newbackup(self, request: Request):
        if self._backup_lock.locked():
            raise HTTPBadRequest()
        input_json = await request.json()
        task = asyncio.shield(asyncio.create_task(self._internalNewBackup(request, input_json)))
        return self._formatDataResponse({"slug": await task})
    
    async def _lock_backups(self, request: Request):
        await self._backup_lock.acquire()
        return self._formatDataResponse({"message": "locked"})

    async def _uploadbackup(self, request: Request):
        await self._verifyHeader(request)
        try:
            reader = await request.multipart()
            contents = await reader.next()
            received_bytes = bytearray()
            while True:
                chunk = await contents.read_chunk()
                if not chunk:
                    break
                received_bytes.extend(chunk)
            info = parseBackupInfo(io.BytesIO(received_bytes))
            self._backups[info['slug']] = info
            self._backup_data[info['slug']] = received_bytes
            return self._formatDataResponse({"slug": info['slug']})
        except Exception as e:
            print(str(e))
            return self._formatErrorResponse("Bad backup")

    async def _deletebackup(self, request: Request):
        await self._verifyHeader(request)
        slug = request.match_info.get('slug')
        if slug not in self._backups:
            raise HTTPNotFound()
        del self._backups[slug]
        del self._backup_data[slug]
        return self._formatDataResponse("deleted")

    async def _backupDetail(self, request: Request):
        await self._verifyHeader(request)
        slug = request.match_info.get('slug')
        if slug not in self._backups:
            raise HTTPNotFound()
        return self._formatDataResponse(self._backups[slug])

    async def _backupDownload(self, request: Request):
        await self._verifyHeader(request)
        slug = request.match_info.get('slug')
        if slug not in self._backup_data:
            raise HTTPNotFound()
        return self.serve_bytes(request, self._backup_data[slug])

    async def _selfInfo(self, request: Request):
        await self._verifyHeader(request)
        return self._formatDataResponse({
            "webui": "http://some/address",
            'ingress_url': "fill me in later",
            "slug": self._addon_slug,
            "options": self._options
        })

    async def _debugInfo(self, request: Request):
        return self._formatDataResponse({
            "config": {
                "   webui": "http://some/address",
                'ingress_url': "fill me in later",
                "slug": self._addon_slug,
                "options": self._options
            }
        })

    async def _miscInfo(self, request: Request):
        await self._verifyHeader(request)
        return self._formatDataResponse({
            "supervisor": "super version",
            "homeassistant": "ha version",
            "hassos": "hassos version",
            "hostname": "hostname",
            "machine": "machine",
            "arch": "Arch",
            "supported_arch": "supported arch",
            "channel": "channel"
        })

    def installAddon(self, slug, name, version="v1.0", boot=True, started=True):
        self._addons.append({
            "name": 'Name for ' + name,
            "slug": slug,
            "description": slug + " description",
            "version": version,
            "watchdog": False,
            "boot": "auto" if boot else "manual",
            "logo": True,
            "ingress_entry": "/api/hassio_ingress/" + slug,
            "state": "started" if started else "stopped"
        })

    async def _authenticate(self, request: Request):
        await self._verifyHeader(request)
        input_json = await request.json()
        if input_json.get("username") != self._username or input_json.get("password") != self._password:
            raise HTTPBadRequest()
        return self._formatDataResponse({})

    async def _updateOptions(self, request: Request):
        slug = request.match_info.get('slug')

        if slug == "self":
            await self._verifyHeader(request)
            self._options = (await request.json())['options'].copy()
        else:
            self.addon(slug).update(await request.json())
        return self._formatDataResponse({})

    async def _haStateUpdate(self, request: Request):
        await self._verifyHeader(request)
        entity = request.match_info.get('entity')
        json = await request.json()
        self._entities[entity] = json['state']
        self._attributes[entity] = json['attributes']
        return Response()

    async def _haStateDelete(self, request: Request):
        await self._verifyHeader(request)
        entity = request.match_info.get('entity')
        if entity not in self._entities:
            raise HTTPNotFound()
        del self._entities[entity]
        self._attributes.pop(entity, None)
        return Response()

    def getRestores(self):
        """The restores requested, as (slug, "full" or "partial", request body)."""
        return self._restores.copy()

    async def _restoreBackup(self, request: Request):
        await self._verifyHeader(request)
        slug = request.match_info.get('slug')
        if slug not in self._backups:
            raise HTTPNotFound()
        body = await request.json()
        expected = self._backup_passwords.get(slug)
        if expected is not None and body.get('password') != expected:
            return self._formatErrorResponse("Invalid password for backup " + slug)
        self._restores.append((slug, request.path.split("/")[-1], body))
        return self._formatDataResponse({"job_id": self.generateId(8)})

    def setMqttService(self, info):
        """Sets the MQTT broker details the supervisor reports, or None when no broker is installed."""
        self._mqtt_service = info

    async def _mqttService(self, request: Request):
        await self._verifyHeader(request)
        if self._mqtt_service is None:
            return self._formatErrorResponse("Service not enabled")
        return self._formatDataResponse(self._mqtt_service)

    async def _haEventUpdate(self, request: Request):
        await self._verifyHeader(request)
        name = request.match_info.get('name')
        self._events.append((name, await request.json()))
        return Response()

    def getSystemLog(self):
        """Messages written to Home Assistant's log, as system_log.write service data."""
        return self._system_log.copy()

    async def _systemLogWrite(self, request: Request):
        await self._verifyHeader(request)
        self._system_log.append(await request.json())
        return Response()

    def getNotifyServiceCalls(self):
        return self._notify_calls.copy()

    async def _notifyService(self, request: Request):
        await self._verifyHeader(request)
        name = request.match_info.get('name')
        if name not in self._notify_services:
            return Response(status=400, text="Service not found")
        self._notify_calls.append((name, await request.json()))
        return Response()

    async def _createNotification(self, request: Request):
        await self._verifyHeader(request)
        notification = await request.json()
        print("Created notification with: {}".format(notification))
        self._notification = notification.copy()
        return Response()

    async def _dismissNotification(self, request: Request):
        await self._verifyHeader(request)
        print("Dismissed notification with: {}".format(await request.json()))
        self._notification = None
        return Response()

    async def _debug_insert_backup(self, request: Request) -> Response:
        days_back = int(request.query.get("days"))
        date = self._time.now() - timedelta(days=days_back)
        name = date.strftime("Full Backup %Y-%m-%d %H:%M-%S")
        wait = int(request.query.get("wait", 0))
        slug = await self._internalNewBackup(request, {'name': name, 'wait': wait}, date=date, verify_header=False)
        return self._formatDataResponse({'slug': slug})

import asyncio
import json
from typing import Any, Dict, Optional

import aiomqtt
from injector import inject, singleton

from ..config import Config, Setting, Startable, VERSION
from ..logger import getLogger
from .harequests import HaRequests

logger = getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"
TOPIC_BASE = "hass_gdrive_backup"
DEVICE_ID = "hass_gdrive_backup"
RETRY_SECONDS = 60
NO_SERVICE_RETRY_SECONDS = 10 * 60
REPOSITORY_URL = "https://github.com/willkpalmer/hass_gdrive_backup"

# Entities the add-on sets through the REST API when MQTT isn't available. Their states are removed
# before MQTT discovery so the discovered entities can take these entity IDs.
REST_ENTITIES = ["binary_sensor.backups_stale", "sensor.backup_state"]


def _timestamp(field: str) -> str:
    # MQTT sensors treat the payload "None" as unknown, which is what a missing timestamp should be.
    return "{{{{ value_json.{0} if value_json.{0} else 'None' }}}}".format(field)


COMPONENTS = {
    "backups_stale": {
        "p": "binary_sensor",
        "name": "Backups stale",
        "device_class": "problem",
        "value_template": "{{ 'ON' if value_json.stale else 'OFF' }}",
        "default_entity_id": "binary_sensor.backups_stale",
    },
    "backup_state": {
        "p": "sensor",
        "name": "Backup state",
        "device_class": "enum",
        "options": ["backed_up", "waiting", "error"],
        "value_template": "{{ value_json.state }}",
        "json_attributes_topic": TOPIC_BASE + "/state",
        "json_attributes_template": "{{ value_json.attributes | tojson }}",
        "default_entity_id": "sensor.backup_state",
    },
    "last_backup": {
        "p": "sensor",
        "name": "Last backup",
        "device_class": "timestamp",
        "value_template": _timestamp("last_backup"),
    },
    "last_upload": {
        "p": "sensor",
        "name": "Last upload",
        "device_class": "timestamp",
        "value_template": _timestamp("last_upload"),
    },
    "next_backup": {
        "p": "sensor",
        "name": "Next backup",
        "device_class": "timestamp",
        "value_template": _timestamp("next_backup"),
    },
    "backups_in_home_assistant": {
        "p": "sensor",
        "name": "Backups in Home Assistant",
        "state_class": "measurement",
        "value_template": "{{ value_json.backups_in_home_assistant }}",
    },
    "backups_in_google_drive": {
        "p": "sensor",
        "name": "Backups in Google Drive",
        "state_class": "measurement",
        "value_template": "{{ value_json.backups_in_google_drive }}",
    },
}


@singleton
class MqttPublisher(Startable):
    """
    Publishes the add-on's sensors through MQTT discovery, so they become real Home Assistant entities
    (with unique IDs, grouped under one device) that survive Home Assistant restarts. Uses the broker
    the Supervisor provides (such as the Mosquitto add-on). When none is available, HaUpdater falls
    back to setting entity states through Home Assistant's REST API.
    """
    @inject
    def __init__(self, config: Config, harequests: HaRequests):
        self._config = config
        self._harequests = harequests
        self._client: Optional[aiomqtt.Client] = None
        self._runner: Optional[asyncio.Task] = None
        self._last_state: Optional[str] = None
        self._service_available: Optional[bool] = None

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def start(self):
        self._runner = asyncio.create_task(self._run(), name="MQTT publisher")

    async def stop(self):
        if self._runner is not None and not self._runner.done():
            self._runner.cancel()
            await asyncio.wait([self._runner])
        self._runner = None

    async def usesMqtt(self) -> bool:
        """True when sensors should go through MQTT (even if it isn't connected yet) instead of the REST API."""
        if not self._config.get(Setting.MQTT_DISCOVERY):
            return False
        if self._service_available is None:
            self._service_available = (await self._serviceInfo()) is not None
        return self._service_available

    async def publishState(self, state: Dict[str, Any]) -> bool:
        """Publishes the sensors' state. Returns False if MQTT isn't connected."""
        payload = json.dumps(state, default=str)
        self._last_state = payload
        client = self._client
        if client is None:
            return False
        try:
            await client.publish(TOPIC_BASE + "/state", payload, qos=1, retain=True)
            return True
        except aiomqtt.MqttError as e:
            logger.debug("Couldn't publish to MQTT: %s", e)
            return False

    def discoveryConfig(self) -> Dict[str, Any]:
        components = {}
        for key, component in COMPONENTS.items():
            components[key] = {**component, "unique_id": DEVICE_ID + "_" + key}
        return {
            "dev": {
                "ids": [DEVICE_ID],
                "name": "GDrive Backup Utility",
                "mf": "hass_gdrive_backup",
                "sw": VERSION,
            },
            "o": {"name": "hass_gdrive_backup", "sw": VERSION, "url": REPOSITORY_URL},
            "avty_t": TOPIC_BASE + "/availability",
            "stat_t": TOPIC_BASE + "/state",
            "qos": 1,
            "cmps": components,
        }

    async def _serviceInfo(self) -> Optional[Dict[str, Any]]:
        if not self._config.get(Setting.MQTT_DISCOVERY):
            return None
        try:
            return await self._harequests.mqttServiceInfo()
        except Exception:
            # Normal when no MQTT broker (such as the Mosquitto add-on) is installed.
            return None

    def _createClient(self, info: Dict[str, Any]) -> aiomqtt.Client:
        return aiomqtt.Client(
            hostname=info["host"],
            port=int(info.get("port", 1883)),
            username=info.get("username"),
            password=info.get("password"),
            identifier="hass_gdrive_backup",
            will=aiomqtt.Will(TOPIC_BASE + "/availability", "offline", qos=1, retain=True),
        )

    async def _run(self):
        while True:
            info = await self._serviceInfo()
            self._service_available = info is not None
            if info is None:
                await asyncio.sleep(NO_SERVICE_RETRY_SECONDS)
                continue
            try:
                await self._connectAndServe(info)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.info("Lost the connection to the MQTT broker, retrying soon: %s", e)
            finally:
                self._client = None
            await asyncio.sleep(RETRY_SECONDS)

    async def _connectAndServe(self, info: Dict[str, Any]):
        async with self._createClient(info) as client:
            for entity in REST_ENTITIES:
                try:
                    await self._harequests.deleteEntityState(entity)
                except Exception as e:
                    logger.debug("Couldn't remove the old state of %s: %s", entity, e)
            await client.publish("{0}/device/{1}/config".format(DISCOVERY_PREFIX, DEVICE_ID),
                                 json.dumps(self.discoveryConfig()), qos=1, retain=True)
            await client.publish(TOPIC_BASE + "/availability", "online", qos=1, retain=True)
            if self._last_state is not None:
                await client.publish(TOPIC_BASE + "/state", self._last_state, qos=1, retain=True)
            logger.info("Publishing sensors to Home Assistant through MQTT")
            self._client = client
            try:
                # Wait here until the connection drops (iterating messages raises when it does).
                async for _ in client.messages:
                    pass
            finally:
                if self._client is client:
                    self._client = None
                    try:
                        await asyncio.wait_for(client.publish(TOPIC_BASE + "/availability", "offline", qos=1, retain=True), 5)
                    except Exception:
                        pass

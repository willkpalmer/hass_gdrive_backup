import asyncio
import json

import pytest

from backup.config import Config, Setting
from backup.ha import HaUpdater, MqttPublisher
from dev.simulated_supervisor import SimulatedSupervisor
from .faketime import FakeTime

BROKER = {"host": "core-mosquitto", "port": 1883, "ssl": False, "protocol": "3.1.1", "username": "addons", "password": "secret"}


class FakeMqttClient():
    def __init__(self, info):
        self.info = info
        self.published = []
        self._disconnect = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))

    def topic(self, topic):
        return [payload for published_topic, payload, _ in self.published if published_topic == topic]

    @property
    def messages(self):
        return self._messages()

    async def _messages(self):
        await self._disconnect.wait()
        raise Exception("disconnected")
        yield


@pytest.fixture
def mqtt(injector, monkeypatch) -> MqttPublisher:
    publisher = injector.get(MqttPublisher)
    publisher.clients = []

    def create(info):
        client = FakeMqttClient(info)
        publisher.clients.append(client)
        return client
    monkeypatch.setattr(publisher, "_createClient", create)
    return publisher


@pytest.mark.asyncio
async def test_rest_sensors_without_broker(updater: HaUpdater, supervisor: SimulatedSupervisor, mqtt: MqttPublisher):
    await updater.update()
    assert not await mqtt.usesMqtt()
    assert supervisor.getEntity("binary_sensor.backups_stale") == "off"


@pytest.mark.asyncio
async def test_mqtt_disabled(updater: HaUpdater, supervisor: SimulatedSupervisor, mqtt: MqttPublisher, config: Config):
    supervisor.setMqttService(BROKER)
    config.override(Setting.MQTT_DISCOVERY, False)
    await updater.update()
    assert not await mqtt.usesMqtt()
    assert supervisor.getEntity("binary_sensor.backups_stale") == "off"


@pytest.mark.asyncio
async def test_sensors_go_through_mqtt(updater: HaUpdater, supervisor: SimulatedSupervisor, mqtt: MqttPublisher, time: FakeTime):
    supervisor.setMqttService(BROKER)
    await updater.update()
    assert await mqtt.usesMqtt()
    # REST states aren't set, so the MQTT entities can have these entity IDs
    assert supervisor.getEntity("binary_sensor.backups_stale") is None
    assert supervisor.getEntity("sensor.backup_state") is None
    state = json.loads(mqtt._last_state)
    assert state["stale"] is False
    assert state["state"] == "waiting"
    assert state["last_backup"] is None
    assert state["next_backup"] == time.now().isoformat()
    assert state["backups_in_google_drive"] == 0
    assert state["attributes"]["friendly_name"] == "Backup State"


@pytest.mark.asyncio
async def test_connect_publishes_discovery(updater: HaUpdater, supervisor: SimulatedSupervisor, mqtt: MqttPublisher):
    supervisor.setMqttService(BROKER)
    # Left over from before MQTT was available
    await mqtt._harequests.updateEntity("binary_sensor.backups_stale", {"state": "off", "attributes": {}})
    await updater.update()

    task = asyncio.create_task(mqtt._connectAndServe(BROKER))
    for _ in range(100):
        if mqtt.connected:
            break
        await asyncio.sleep(0.01)
    assert mqtt.connected
    client: FakeMqttClient = mqtt.clients[0]
    assert client.info == BROKER
    assert supervisor.getEntity("binary_sensor.backups_stale") is None

    discovery = json.loads(client.topic("homeassistant/device/hass_gdrive_backup/config")[0])
    assert discovery["dev"]["ids"] == ["hass_gdrive_backup"]
    assert discovery["o"]["name"] == "hass_gdrive_backup"
    assert discovery["stat_t"] == "hass_gdrive_backup/state"
    for key, component in discovery["cmps"].items():
        assert component["p"] in ["sensor", "binary_sensor"]
        assert component["unique_id"] == "hass_gdrive_backup_" + key
    assert discovery["cmps"]["backups_stale"]["default_entity_id"] == "binary_sensor.backups_stale"
    assert client.topic("hass_gdrive_backup/availability") == ["online"]
    # The state published before connecting is sent once connected
    assert json.loads(client.topic("hass_gdrive_backup/state")[0])["state"] == "waiting"

    await updater.update()
    assert len(client.topic("hass_gdrive_backup/state")) == 2

    client._disconnect.set()
    with pytest.raises(Exception):
        await task
    assert not mqtt.connected
    assert client.topic("hass_gdrive_backup/availability") == ["online", "offline"]

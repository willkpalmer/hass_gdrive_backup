import asyncio
from datetime import timedelta

import pytest

from backup.config import Config, Setting, CreateOptions
from backup.ha import HaSource, CoreBackups, HomeAssistantWebsocketError
from backup.model import Coordinator, Model
from dev.simulated_supervisor import SimulatedSupervisor
from .faketime import FakeTime


def haSchedule(supervisor: SimulatedSupervisor, time: FakeTime, **schedule):
    supervisor.setCoreBackupConfig(
        automatic_backups_configured=True,
        schedule={"recurrence": "daily", **schedule},
        next_automatic_backup=(time.now() + timedelta(hours=5)).isoformat())


@pytest.mark.asyncio
async def test_auto_mode_without_ha_schedule(ha: HaSource, config: Config, supervisor: SimulatedSupervisor):
    await ha.get()
    assert ha.coreBackups.available
    assert not ha.coreBackups.schedulesBackups
    assert ha.schedulesOwnBackups()
    assert ha.maxCount() == config.get(Setting.MAX_BACKUPS_IN_HA)


@pytest.mark.asyncio
async def test_auto_mode_follows_ha_schedule(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime, coord: Coordinator):
    haSchedule(supervisor, time)
    await ha.get()
    assert ha.coreBackups.schedulesBackups
    assert not ha.schedulesOwnBackups()
    # Home Assistant's retention manages local backups
    assert ha.maxCount() == 0
    assert coord.nextBackupTime() == time.now() + timedelta(hours=5)


@pytest.mark.asyncio
async def test_auto_mode_without_websocket(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime):
    haSchedule(supervisor, time)
    supervisor.setCoreWebsocketAvailable(False)
    await ha.get()
    assert not ha.coreBackups.available
    assert ha.schedulesOwnBackups()


@pytest.mark.asyncio
async def test_addon_mode_ignores_ha_schedule(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime, config: Config):
    config.override(Setting.BACKUP_MODE, "addon")
    config.override(Setting.IGNORE_OTHER_BACKUPS, True)
    haSchedule(supervisor, time)
    slug = await supervisor.createAutomaticBackup()
    backups = await ha.get()
    assert ha.schedulesOwnBackups()
    assert backups[slug].ignore()


@pytest.mark.asyncio
async def test_adopts_ha_automatic_backups(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime, config: Config):
    config.override(Setting.IGNORE_OTHER_BACKUPS, True)
    haSchedule(supervisor, time)
    automatic = await supervisor.createAutomaticBackup()
    other = await supervisor.createBackup({"name": "Made by someone else"})
    backups = await ha.get()
    assert not backups[automatic].ignore()
    assert backups[other].ignore()


@pytest.mark.asyncio
async def test_model_doesnt_schedule_when_ha_does(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime, model: Model, config: Config):
    config.override(Setting.DAYS_BETWEEN_BACKUPS, 1)
    haSchedule(supervisor, time)
    await model.sync(time.now())
    assert len(await ha.get()) == 0
    assert model.nextBackup(time.now()) is None


@pytest.mark.asyncio
async def test_backup_now_asks_home_assistant(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime):
    haSchedule(supervisor, time)
    supervisor.setCoreBackupConfig(create_backup={"password": "ha key", "name": "Nightly"})
    backup = await ha.create(CreateOptions(time.now(), "Ignored name"))
    assert backup.isHomeAssistantAutomatic()
    assert backup.name() == "Nightly"
    assert backup.protected()
    backups = await ha.get()
    assert len(backups) == 1
    assert not backups[backup.slug()].ignore()


@pytest.mark.asyncio
async def test_home_assistant_mode_needs_websocket(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime, config: Config):
    config.override(Setting.BACKUP_MODE, "home_assistant")
    supervisor.setCoreWebsocketAvailable(False)
    with pytest.raises(HomeAssistantWebsocketError):
        await ha.create(CreateOptions(time.now(), "Test"))


@pytest.mark.asyncio
async def test_addon_backups_use_ha_encryption_key(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime, config: Config):
    supervisor.setCoreBackupConfig(create_backup={"password": "ha key"})
    backup = await ha.create(CreateOptions(time.now(), "Encrypted"))
    assert backup.protected()

    config.override(Setting.USE_HOME_ASSISTANT_ENCRYPTION_KEY, False)
    time.advance(minutes=5)
    backup = await ha.create(CreateOptions(time.now(), "Not encrypted"))
    assert not backup.protected()


@pytest.mark.asyncio
async def test_backup_password_wins_over_ha_key(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime, config: Config):
    supervisor.setCoreBackupConfig(create_backup={"password": "ha key"})
    config.override(Setting.BACKUP_PASSWORD, "my password")
    request, _, protected = await ha_request(ha, time)
    assert protected
    assert request["password"] == "my password"


async def ha_request(ha: HaSource, time: FakeTime):
    await ha.init()
    await ha.coreBackups.refresh()
    return ha._buildBackupInfo(CreateOptions(time.now(), "Name"))


@pytest.mark.asyncio
async def test_backup_due_by(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime, coord: Coordinator):
    core: CoreBackups = ha.coreBackups
    last = time.now() - timedelta(hours=2)
    haSchedule(supervisor, time)
    supervisor.setCoreBackupConfig(last_completed_automatic_backup=last.isoformat())
    await ha.get()
    assert core.backupDueBy() == last + timedelta(days=1)
    assert coord.backupDueBy() == last + timedelta(days=1)

    # The longest gap between Monday and Thursday backups is Thursday -> Monday
    supervisor.setCoreBackupConfig(schedule={"recurrence": "custom_days", "days": ["mon", "thu"]})
    await ha.get()
    assert core.backupDueBy() == last + timedelta(days=4)

    supervisor.setCoreBackupConfig(schedule={"recurrence": "never"})
    await ha.get()
    assert core.backupDueBy() is None


@pytest.mark.asyncio
async def test_completed_backup_event_triggers_sync(ha: HaSource, supervisor: SimulatedSupervisor, time: FakeTime):
    await ha.get()
    ha.reset()
    await supervisor._coreEvent({"manager_state": "create_backup", "stage": None, "state": "in_progress", "reason": None})
    await asyncio.sleep(0.1)
    assert not ha.triggered()
    await supervisor._coreEvent({"manager_state": "create_backup", "stage": None, "state": "completed", "reason": None})
    await asyncio.sleep(0.1)
    assert ha.triggered()


@pytest.mark.asyncio
async def test_status_reports_ha_schedule(reader, supervisor: SimulatedSupervisor, time: FakeTime, coord: Coordinator):
    status = await reader.getjson("getstatus")
    assert not status['home_assistant_backups']['scheduling']

    haSchedule(supervisor, time)
    supervisor.setCoreBackupConfig(retention={"copies": 5, "days": None})
    await coord.sync()
    status = await reader.getjson("getstatus")
    assert status['home_assistant_backups'] == {
        'scheduling': True,
        'available': True,
        'retention': "Home Assistant keeps the latest 5",
    }
    assert status['next_backup_machine'] == time.asRfc3339String(time.now() + timedelta(hours=5))

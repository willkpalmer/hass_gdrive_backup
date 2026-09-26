import pytest

from backup.config import Config, Setting
from backup.ha import HaUpdater
from backup.util import GlobalInfo
from dev.simulated_supervisor import SimulatedSupervisor
from .faketime import FakeTime


@pytest.mark.asyncio
async def test_no_notify_service_by_default(updater: HaUpdater, time: FakeTime, global_info: GlobalInfo, supervisor: SimulatedSupervisor):
    global_info.failed(Exception())
    time.advance(hours=8)
    await updater.update()
    assert supervisor.getNotification() is not None
    assert supervisor.getNotifyServiceCalls() == []


@pytest.mark.asyncio
async def test_notify_service_problem_and_recovery(updater: HaUpdater, time: FakeTime, global_info: GlobalInfo, supervisor: SimulatedSupervisor, config: Config):
    config.override(Setting.NOTIFY_SERVICE, "notify.mobile_app_phone")
    global_info.url = "/hassio/ingress/hass_gdrive_backup"
    await updater.update()
    assert supervisor.getNotifyServiceCalls() == []

    global_info.failed(Exception())
    time.advance(hours=8)
    await updater.update()
    await updater.update()
    calls = supervisor.getNotifyServiceCalls()
    assert len(calls) == 1
    name, data = calls[0]
    assert name == "mobile_app_phone"
    assert data["title"] == "Backups need attention"
    assert data["data"]["url"] == "/hassio/ingress/hass_gdrive_backup"

    global_info.success()
    await updater.update()
    calls = supervisor.getNotifyServiceCalls()
    assert len(calls) == 2
    assert calls[1][1]["title"] == "Backups are working again"


@pytest.mark.asyncio
async def test_notify_service_without_prefix(updater: HaUpdater, time: FakeTime, global_info: GlobalInfo, supervisor: SimulatedSupervisor, config: Config):
    config.override(Setting.NOTIFY_SERVICE, "mobile_app_phone")
    global_info.failed(Exception())
    time.advance(hours=8)
    await updater.update()
    assert supervisor.getNotifyServiceCalls()[0][0] == "mobile_app_phone"


@pytest.mark.asyncio
async def test_bad_notify_service_doesnt_break_sensors(updater: HaUpdater, time: FakeTime, global_info: GlobalInfo, supervisor: SimulatedSupervisor, config: Config):
    config.override(Setting.NOTIFY_SERVICE, "notify.no_such_phone")
    global_info.failed(Exception())
    time.advance(hours=8)
    await updater.update()
    assert supervisor.getEntity("binary_sensor.backups_stale") == "on"
    assert supervisor.getNotification() is not None
    assert supervisor.getNotifyServiceCalls() == []

    # It keeps trying on later updates, in case the service shows up
    supervisor._notify_services.add("no_such_phone")
    await updater.update()
    assert len(supervisor.getNotifyServiceCalls()) == 1

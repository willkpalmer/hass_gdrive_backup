import pytest

from backup.config import Config, Setting
from backup.ha import HaSource
from backup.model import Coordinator
from backup.ui import UiServer
from backup.util import GlobalInfo
from backup.const import SOURCE_HA, SOURCE_GOOGLE_DRIVE
from dev.simulated_supervisor import SimulatedSupervisor
from .conftest import ReaderHelper


async def makeBackup(coord: Coordinator):
    await coord.sync()
    backups = coord.backups()
    assert len(backups) == 1
    return backups[0]


async def restore(reader: ReaderHelper, ui_server: UiServer, body, status=200):
    await reader.postjson("restore", json=body, status=status)
    if status == 200:
        await ui_server._restore_task


@pytest.mark.asyncio
async def test_full_restore(reader: ReaderHelper, ui_server: UiServer, coord: Coordinator, supervisor: SimulatedSupervisor):
    backup = await makeBackup(coord)
    await restore(reader, ui_server, {"slug": backup.slug()})
    assert supervisor.getRestores() == [(backup.slug(), "full", {"background": True})]


@pytest.mark.asyncio
async def test_partial_restore(reader: ReaderHelper, ui_server: UiServer, coord: Coordinator, supervisor: SimulatedSupervisor):
    backup = await makeBackup(coord)
    await restore(reader, ui_server, {"slug": backup.slug(), "partial": {"homeassistant": True, "folders": ["ssl"], "addons": ["42"]}})
    assert supervisor.getRestores() == [(backup.slug(), "partial", {
        "homeassistant": True, "folders": ["ssl"], "addons": ["42"], "background": True})]


@pytest.mark.asyncio
async def test_partial_restore_needs_a_selection(reader: ReaderHelper, ui_server: UiServer, coord: Coordinator, supervisor: SimulatedSupervisor):
    backup = await makeBackup(coord)
    await restore(reader, ui_server, {"slug": backup.slug(), "partial": {"homeassistant": False}}, status=400)
    assert supervisor.getRestores() == []


@pytest.mark.asyncio
async def test_restore_from_google_drive(reader: ReaderHelper, ui_server: UiServer, coord: Coordinator, supervisor: SimulatedSupervisor, ha: HaSource):
    backup = await makeBackup(coord)
    slug = backup.slug()
    await ha.delete(backup)
    await coord.sync()
    backup = coord.getBackup(slug)
    assert backup.getSource(SOURCE_HA) is None
    assert backup.getSource(SOURCE_GOOGLE_DRIVE) is not None

    await restore(reader, ui_server, {"slug": slug})
    # It was copied back into Home Assistant, then restored
    assert coord.getBackup(slug).getSource(SOURCE_HA) is not None
    assert supervisor.getRestores() == [(slug, "full", {"background": True})]


@pytest.mark.asyncio
async def test_restore_uses_ha_encryption_key(reader: ReaderHelper, ui_server: UiServer, coord: Coordinator, supervisor: SimulatedSupervisor):
    supervisor.setCoreBackupConfig(create_backup={"password": "ha key"})
    backup = await makeBackup(coord)
    assert backup.protected()
    await restore(reader, ui_server, {"slug": backup.slug()})
    assert supervisor.getRestores() == [(backup.slug(), "full", {"background": True, "password": "ha key"})]


@pytest.mark.asyncio
async def test_restore_uses_backup_password(reader: ReaderHelper, ui_server: UiServer, coord: Coordinator, supervisor: SimulatedSupervisor, config: Config):
    config.override(Setting.BACKUP_PASSWORD, "my password")
    backup = await makeBackup(coord)
    await restore(reader, ui_server, {"slug": backup.slug()})
    assert supervisor.getRestores()[0][2]["password"] == "my password"


@pytest.mark.asyncio
async def test_wrong_password_reports_error(reader: ReaderHelper, ui_server: UiServer, coord: Coordinator, supervisor: SimulatedSupervisor, config: Config, global_info: GlobalInfo):
    config.override(Setting.BACKUP_PASSWORD, "my password")
    backup = await makeBackup(coord)
    global_info.success()
    await restore(reader, ui_server, {"slug": backup.slug(), "password": "not it"})
    assert supervisor.getRestores() == []
    assert global_info._last_error is not None


@pytest.mark.asyncio
async def test_restore_dialog_in_page(reader: ReaderHelper, ui_server: UiServer, coord: Coordinator):
    await makeBackup(coord)
    page = await reader.get("")
    assert 'id="restoremodal"' in page
    status = await reader.getjson("getstatus")
    assert status["backups"][0]["restorable"]

import io
import os
import shutil
import tarfile
from datetime import timedelta

import pytest

from backup.config import Config, Setting
from backup.esphome import EsphomeBackup
from backup.esphome.esphomebackup import PROP_KIND, KIND_BACKUP, KIND_FOLDER
from backup.exceptions import UploadVerificationFailed
from backup.model import Coordinator
from dev.simulated_google import SimulatedGoogle
from .conftest import ReaderHelper
from .faketime import FakeTime

FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'


@pytest.fixture
def esphome_dir(config: Config):
    path = config.get(Setting.ESPHOME_PATH)
    os.makedirs(os.path.join(path, ".esphome", "build"))
    with open(os.path.join(path, "kitchen.yaml"), "w") as f:
        f.write("esphome:\n  name: kitchen\n")
    with open(os.path.join(path, "secrets.yaml"), "w") as f:
        f.write("wifi_password: hunter2\n")
    with open(os.path.join(path, ".esphome", "build", "firmware.bin"), "wb") as f:
        f.write(b"\0" * 1024)
    return path


@pytest.fixture
def esphome(injector, config: Config, esphome_dir, server) -> EsphomeBackup:
    config.override(Setting.ESPHOME_BACKUP, True)
    return injector.get(EsphomeBackup)


def driveItems(google: SimulatedGoogle, kind):
    return [item for item in google.items.values() if (item.get("appProperties") or {}).get(PROP_KIND) == kind and not item.get("trashed")]


def archiveNames(item):
    with tarfile.open(fileobj=io.BytesIO(bytes(item["bytes"])), mode="r:gz") as tar:
        return sorted(tar.getnames())


@pytest.mark.asyncio
async def test_backup_to_its_own_folder(esphome: EsphomeBackup, google: SimulatedGoogle):
    assert await esphome.backup() == "uploaded"
    folders = driveItems(google, KIND_FOLDER)
    assert [folder["name"] for folder in folders] == ["ESPHome Backups"]
    assert folders[0]["mimeType"] == FOLDER_MIME_TYPE
    backups = driveItems(google, KIND_BACKUP)
    assert len(backups) == 1
    assert backups[0]["parents"] == [folders[0]["id"]]
    assert backups[0]["name"].startswith("ESPHome ") and backups[0]["name"].endswith(".tar.gz")
    # The build cache isn't included
    assert archiveNames(backups[0]) == ["esphome/kitchen.yaml", "esphome/secrets.yaml"]


@pytest.mark.asyncio
async def test_unchanged_config_isnt_uploaded_again(esphome: EsphomeBackup, google: SimulatedGoogle, esphome_dir, time: FakeTime):
    await esphome.backup()
    time.advance(hours=1)
    assert await esphome.backup() == "unchanged"
    assert len(driveItems(google, KIND_BACKUP)) == 1

    with open(os.path.join(esphome_dir, "garage.yaml"), "w") as f:
        f.write("esphome:\n  name: garage\n")
    time.advance(hours=1)
    assert await esphome.backup() == "uploaded"
    assert len(driveItems(google, KIND_BACKUP)) == 2

    # Backing up on request uploads even when nothing changed
    time.advance(hours=1)
    assert await esphome.backup(force=True) == "uploaded"
    assert len(driveItems(google, KIND_BACKUP)) == 3


@pytest.mark.asyncio
async def test_old_backups_are_deleted(esphome: EsphomeBackup, google: SimulatedGoogle, config: Config, time: FakeTime):
    config.override(Setting.ESPHOME_MAX_BACKUPS, 2)
    for _ in range(4):
        await esphome.backup(force=True)
        time.advance(hours=1)
    backups = driveItems(google, KIND_BACKUP)
    assert len(backups) == 2


@pytest.mark.asyncio
async def test_follows_main_backups(esphome: EsphomeBackup, google: SimulatedGoogle, coord: Coordinator, time: FakeTime):
    assert not esphome.isDue(time.now())
    await coord.sync()
    assert len(coord.backups()) == 1
    assert esphome.isDue(time.now())
    await esphome.check()
    assert len(driveItems(google, KIND_BACKUP)) == 1
    assert not esphome.isDue(time.now())

    # A new main backup makes it due again
    time.advance(days=4)
    await coord.sync()
    assert esphome.isDue(time.now())


@pytest.mark.asyncio
async def test_own_schedule(esphome: EsphomeBackup, google: SimulatedGoogle, config: Config, time: FakeTime):
    config.override(Setting.ESPHOME_SCHEDULE, "own_schedule")
    config.override(Setting.ESPHOME_DAYS_BETWEEN_BACKUPS, 2)
    assert esphome.isDue(time.now())
    await esphome.check()
    assert len(driveItems(google, KIND_BACKUP)) == 1
    assert esphome.nextBackup() == time.now() + timedelta(days=2)
    time.advance(days=1)
    assert not esphome.isDue(time.now())
    time.advance(days=1)
    assert esphome.isDue(time.now())


@pytest.mark.asyncio
async def test_own_schedule_time_of_day(esphome: EsphomeBackup, config: Config, time: FakeTime):
    config.override(Setting.ESPHOME_SCHEDULE, "own_schedule")
    config.override(Setting.ESPHOME_DAYS_BETWEEN_BACKUPS, 1)
    config.override(Setting.ESPHOME_BACKUP_TIME_OF_DAY, "03:30")
    await esphome.backup()
    next_local = time.toLocal(esphome.nextBackup())
    last_local = time.toLocal(esphome.lastBackup())
    assert (next_local.hour, next_local.minute) == (3, 30)
    assert next_local.date() == last_local.date() + timedelta(days=1)


@pytest.mark.asyncio
async def test_disabled_does_nothing(esphome: EsphomeBackup, google: SimulatedGoogle, config: Config, coord: Coordinator):
    config.override(Setting.ESPHOME_BACKUP, False)
    await coord.sync()
    await esphome.check()
    assert driveItems(google, KIND_BACKUP) == []


@pytest.mark.asyncio
async def test_missing_folder_is_reported(esphome: EsphomeBackup, esphome_dir, config: Config, time: FakeTime):
    shutil.rmtree(esphome_dir)
    config.override(Setting.ESPHOME_SCHEDULE, "own_schedule")
    await esphome.check()
    status = esphome.status()
    assert "doesn't exist" in status["last_error"]
    # It waits before trying again
    assert esphome._retry_after == time.now() + timedelta(hours=1)


@pytest.mark.asyncio
async def test_folder_is_reused_or_changed(esphome: EsphomeBackup, google: SimulatedGoogle, config: Config, time: FakeTime):
    await esphome.backup(force=True)
    time.advance(hours=1)
    await esphome.backup(force=True)
    assert len(driveItems(google, KIND_FOLDER)) == 1

    config.override(Setting.ESPHOME_DRIVE_FOLDER, "Other Folder")
    time.advance(hours=1)
    await esphome.backup(force=True)
    folders = {folder["name"]: folder["id"] for folder in driveItems(google, KIND_FOLDER)}
    assert set(folders) == {"ESPHome Backups", "Other Folder"}
    newest = max(driveItems(google, KIND_BACKUP), key=lambda item: item["appProperties"]["hass_gdrive_backup_date"])
    assert newest["parents"] == [folders["Other Folder"]]


@pytest.mark.asyncio
async def test_corrupt_upload_is_removed(esphome: EsphomeBackup, google: SimulatedGoogle):
    google.corrupt_uploads = True
    with pytest.raises(UploadVerificationFailed):
        await esphome.backup()
    assert driveItems(google, KIND_BACKUP) == []


@pytest.mark.asyncio
async def test_status_and_backup_now(reader: ReaderHelper, ui_server, esphome: EsphomeBackup, google: SimulatedGoogle):
    status = await reader.getjson("getstatus")
    assert status["esphome"]["enabled"]
    assert status["esphome"]["last_backup"] is None

    await reader.getjson("esphomebackup")
    await ui_server._esphome_task
    status = await reader.getjson("getstatus")
    assert status["esphome"]["last_backup"] is not None
    assert status["esphome"]["last_file"].startswith("ESPHome ")
    assert len(driveItems(google, KIND_BACKUP)) == 1

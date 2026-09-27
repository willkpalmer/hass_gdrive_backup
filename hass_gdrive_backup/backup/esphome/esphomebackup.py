import asyncio
import io
import os
import tarfile
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from injector import inject, singleton

from ..config import Config, Setting
from ..drive.driverequests import DriveRequests, UploadHasher, FOLDER_MIME_TYPE
from ..exceptions import KnownError, LogicError, UploadVerificationFailed
from ..file import JsonFileSaver
from ..logger import getLogger
from ..model import Coordinator
from ..time import Time
from ..worker import Worker

logger = getLogger(__name__)

SCHEDULE_WITH_BACKUPS = "with_backups"
SCHEDULE_OWN = "own_schedule"

CHECK_INTERVAL_SECONDS = 60
RETRY_AFTER_ERROR = timedelta(hours=1)
MIME_TYPE = "application/gzip"

# Marks the folders and files in Google Drive that this feature manages
PROP_KIND = "hass_gdrive_backup_kind"
KIND_FOLDER = "esphome_folder"
KIND_BACKUP = "esphome_backup"
PROP_DATE = "hass_gdrive_backup_date"

# ESPHome's build cache: large, and rebuilt from the configuration anyway
EXCLUDED_DIRECTORIES = {".esphome", "__pycache__"}

KEY_FOLDER_ID = "folder_id"
KEY_FOLDER_NAME = "folder_name"
KEY_CHOSEN_FOLDER_ID = "chosen_folder_id"
KEY_LAST_BACKUP = "last_backup"
KEY_LAST_FILE = "last_file"


def describe(e: Exception) -> str:
    """KnownErrors keep their message in message() rather than str()."""
    if isinstance(e, KnownError):
        return e.message()
    return str(e)


class BytesStream():
    """An in-memory file in the form DriveRequests.create uploads."""

    def __init__(self, data: bytes):
        self._data = data
        self._position = 0

    def size(self) -> int:
        return len(self._data)

    def position(self, pos=None):
        if pos is not None:
            self._position = pos
        return self._position

    async def read(self, count: int) -> io.BytesIO:
        chunk = self._data[self._position:self._position + count]
        self._position += len(chunk)
        return io.BytesIO(chunk)


@singleton
class EsphomeBackup(Worker):
    """
    Optionally backs up the ESPHome add-on's configuration folder (/config/esphome) to its own folder
    in Google Drive, either after each new main backup or on its own schedule.
    """
    @inject
    def __init__(self, config: Config, time: Time, drive: DriveRequests, coordinator: Coordinator):
        super().__init__("ESPHome Backup", self.check, time, CHECK_INTERVAL_SECONDS)
        self._config = config
        self._time = time
        self._drive = drive
        self._coordinator = coordinator
        self._lock = asyncio.Lock()
        self._state: Dict[str, Any] = self._loadState()
        self._last_error: Optional[Exception] = None
        self._retry_after: Optional[datetime] = None

    def enabled(self) -> bool:
        return self._config.get(Setting.ESPHOME_BACKUP)

    async def check(self) -> None:
        """Runs a backup if one is due. Called periodically by the worker."""
        if not self.enabled() or not self._drive.enabled():
            return
        now = self._time.now()
        if self._retry_after is not None and now < self._retry_after:
            return
        if self.isDue(now):
            if self._config.get(Setting.ESPHOME_SCHEDULE) == SCHEDULE_OWN:
                logger.info("An ESPHome backup is due")
            else:
                logger.info("There's a new backup, so backing up the ESPHome configuration too")
            try:
                await self.backup()
            except Exception:
                # Already logged; try again later rather than every minute.
                self._retry_after = now + RETRY_AFTER_ERROR

    def isDue(self, now: datetime) -> bool:
        if self._config.get(Setting.ESPHOME_SCHEDULE) == SCHEDULE_OWN:
            next_backup = self.nextBackup()
            return next_backup is not None and now >= next_backup
        latest = self._latestMainBackup()
        last = self.lastBackup()
        return latest is not None and (last is None or latest > last)

    def lastBackup(self) -> Optional[datetime]:
        if KEY_LAST_BACKUP not in self._state:
            return None
        return self._time.parse(self._state[KEY_LAST_BACKUP])

    def nextBackup(self) -> Optional[datetime]:
        """When the next backup is planned, on its own schedule. None when it follows the main backups."""
        if self._config.get(Setting.ESPHOME_SCHEDULE) != SCHEDULE_OWN:
            return None
        days = self._config.get(Setting.ESPHOME_DAYS_BETWEEN_BACKUPS)
        if days <= 0:
            return None
        last = self.lastBackup()
        if last is None:
            return self._time.now()
        time_of_day = self._parseTimeOfDay(self._config.get(Setting.ESPHOME_BACKUP_TIME_OF_DAY))
        if time_of_day is None:
            return last + timedelta(days=days)
        last_local = self._time.toLocal(last)
        next_date = date.fromordinal(last_local.toordinal() + max(1, int(days)))
        return self._time.toUtc(self._time.localize(datetime(next_date.year, next_date.month, next_date.day, time_of_day[0], time_of_day[1])))

    async def backup(self) -> None:
        """Backs up the ESPHome folder to Google Drive."""
        async with self._lock:
            try:
                await self._backup()
                self._last_error = None
                self._retry_after = None
            except Exception as e:
                self._last_error = e
                logger.error("Couldn't back up the ESPHome configuration: {0}".format(describe(e)))
                raise

    async def _backup(self) -> None:
        now = self._time.now()
        path = self._config.get(Setting.ESPHOME_PATH)
        if not os.path.isdir(path):
            raise FileNotFoundError("{0} doesn't exist. Is the ESPHome add-on installed?".format(path))
        files = await asyncio.get_running_loop().run_in_executor(None, self._listFiles, path)
        data = await asyncio.get_running_loop().run_in_executor(None, self._archive, path, files)
        folder_id = await self._folder()
        name = "ESPHome {0}.tar.gz".format(self._time.toLocal(now).strftime("%Y-%m-%d %H-%M-%S"))
        metadata = {
            'name': name,
            'parents': [folder_id],
            'description': "ESPHome configuration backed up by GDrive Backup Utility",
            'appProperties': {PROP_KIND: KIND_BACKUP, PROP_DATE: now.isoformat()},
        }
        logger.info("Uploading the ESPHome configuration to Google Drive as '{0}'".format(name))
        hasher = UploadHasher()
        uploaded = None
        async for progress in self._drive.create(BytesStream(data), metadata, MIME_TYPE, hasher=hasher):
            if not isinstance(progress, float):
                uploaded = progress
        if uploaded is not None and uploaded.get("md5Checksum") and hasher.hexdigest() != uploaded.get("md5Checksum"):
            await self._drive.delete(uploaded["id"])
            raise UploadVerificationFailed(name)

        self._state[KEY_LAST_BACKUP] = now.isoformat()
        self._state[KEY_LAST_FILE] = name
        self._state.pop("fingerprint", None)
        self._saveState()
        await self._cleanUp(folder_id)
        logger.info("Backed up the ESPHome configuration ({0} files) to Google Drive".format(len(files)))

    def status(self) -> Dict[str, Any]:
        next_backup = self.nextBackup()
        return {
            'enabled': self.enabled(),
            'schedule': self._config.get(Setting.ESPHOME_SCHEDULE),
            'folder_id': self.currentFolder(),
            'last_backup': self._state.get(KEY_LAST_BACKUP),
            'last_file': self._state.get(KEY_LAST_FILE),
            'next_backup': next_backup.isoformat() if next_backup else None,
            'last_error': describe(self._last_error) if self._last_error else None,
        }

    def _latestMainBackup(self) -> Optional[datetime]:
        backups = [backup for backup in self._coordinator.backups() if not backup.ignore() and not backup.isPending()]
        if len(backups) == 0:
            return None
        return max(backup.date() for backup in backups)

    def chosenFolder(self) -> Optional[str]:
        """The Google Drive folder ID chosen in the settings, used when esphome_specify_folder is on."""
        return self._state.get(KEY_CHOSEN_FOLDER_ID)

    def setChosenFolder(self, folder_id: str) -> None:
        folder_id = folder_id.strip()
        if folder_id == self.chosenFolder():
            return
        logger.info("Saving the ESPHome backup folder: {0}".format(folder_id))
        self._state[KEY_CHOSEN_FOLDER_ID] = folder_id
        self._saveState()

    def currentFolder(self) -> Optional[str]:
        """The Google Drive folder ESPHome backups go into, if it's known yet."""
        if self._config.get(Setting.ESPHOME_SPECIFY_FOLDER):
            return self.chosenFolder()
        if self._state.get(KEY_FOLDER_NAME) == self._config.get(Setting.ESPHOME_DRIVE_FOLDER):
            return self._state.get(KEY_FOLDER_ID)
        return None

    async def _folder(self) -> str:
        """The chosen Google Drive folder for ESPHome backups, or else one the add-on finds or creates."""
        if self._config.get(Setting.ESPHOME_SPECIFY_FOLDER):
            folder_id = self.chosenFolder()
            if not folder_id:
                raise LogicError("No Google Drive folder has been chosen for ESPHome backups. Choose one in the settings.")
            try:
                folder = await self._drive.get(folder_id)
            except Exception as e:
                raise LogicError("Couldn't open the Google Drive folder chosen for ESPHome backups ({0}). Choose it again in the settings with the 'Choose Folder' button.".format(e))
            if folder.get("trashed", False):
                raise LogicError("The Google Drive folder chosen for ESPHome backups is in the trash. Choose another in the settings.")
            return folder["id"]
        name = self._config.get(Setting.ESPHOME_DRIVE_FOLDER)
        if self._state.get(KEY_FOLDER_ID) and self._state.get(KEY_FOLDER_NAME) == name:
            try:
                folder = await self._drive.get(self._state[KEY_FOLDER_ID])
                if not folder.get("trashed", False):
                    return folder["id"]
            except Exception as e:
                logger.info("The ESPHome backup folder isn't available any more ({0}), so looking for another".format(e))
        folder_id = None
        async for item in self._drive.query("mimeType='" + FOLDER_MIME_TYPE + "'"):
            if item.get("name") == name and not item.get("trashed", False) and (item.get("appProperties") or {}).get(PROP_KIND) == KIND_FOLDER:
                folder_id = item["id"]
                break
        if folder_id is None:
            logger.info("Creating the Google Drive folder '{0}' for ESPHome backups".format(name))
            created = await self._drive.createFolder({
                'name': name,
                'mimeType': FOLDER_MIME_TYPE,
                'appProperties': {PROP_KIND: KIND_FOLDER},
            })
            folder_id = created["id"]
        self._state[KEY_FOLDER_ID] = folder_id
        self._state[KEY_FOLDER_NAME] = name
        self._saveState()
        return folder_id

    async def _cleanUp(self, folder_id: str) -> None:
        keep = self._config.get(Setting.ESPHOME_MAX_BACKUPS)
        if keep <= 0:
            return
        backups = []
        async for item in self._drive.query("'" + folder_id + "' in parents"):
            properties = item.get("appProperties") or {}
            if properties.get(PROP_KIND) == KIND_BACKUP and not item.get("trashed", False):
                backups.append((properties.get(PROP_DATE, ""), item))
        backups.sort(key=lambda entry: entry[0])
        for _, item in backups[:max(0, len(backups) - keep)]:
            logger.info("Deleting the old ESPHome backup '{0}' from Google Drive".format(item.get("name")))
            await self._drive.delete(item["id"])

    @staticmethod
    def _listFiles(path: str) -> List[Tuple[str, str]]:
        """(relative path, full path) of every file to back up."""
        files = []
        for root, directories, names in os.walk(path):
            directories[:] = sorted(d for d in directories if d not in EXCLUDED_DIRECTORIES)
            for name in sorted(names):
                full = os.path.join(root, name)
                if not os.path.isfile(full):
                    continue
                files.append((os.path.relpath(full, path), full))
        return files

    @staticmethod
    def _archive(path: str, files) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for relative, full in files:
                tar.add(full, arcname=os.path.join("esphome", relative), recursive=False)
        return buffer.getvalue()

    def _parseTimeOfDay(self, value: str) -> Optional[Tuple[int, int]]:
        try:
            hours, minutes = value.split(":")
            hours, minutes = int(hours), int(minutes)
            if 0 <= hours < 24 and 0 <= minutes < 60:
                return hours, minutes
        except ValueError:
            pass
        return None

    def _loadState(self) -> Dict[str, Any]:
        path = self._config.get(Setting.ESPHOME_STATE_PATH)
        try:
            if JsonFileSaver.exists(path):
                return JsonFileSaver.read(path)
        except Exception as e:
            logger.warning("Couldn't read the ESPHome backup state, starting fresh: {0}".format(e))
        return {}

    def _saveState(self) -> None:
        JsonFileSaver.write(self._config.get(Setting.ESPHOME_STATE_PATH), self._state)

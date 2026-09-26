from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from injector import inject, singleton

from ..config import Config, Setting
from ..logger import getLogger
from ..time import Time
from .hawebsocket import HaWebsocket, HomeAssistantWebsocketError

logger = getLogger(__name__)

BACKUP_MODE_AUTO = "auto"
BACKUP_MODE_HOME_ASSISTANT = "home_assistant"
BACKUP_MODE_ADDON = "addon"

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@singleton
class CoreBackups():
    """
    Home Assistant Core's own backup system (Settings > System > Backups): its automatic backup
    schedule, retention and encryption key, read through the websocket API.

    The add-on can defer to it (see Setting.BACKUP_MODE). When it does, Home Assistant decides when
    backups are made and how many stay on the device, and the add-on uploads its automatic backups
    to Google Drive and manages what's kept there.
    """
    @inject
    def __init__(self, config: Config, websocket: HaWebsocket, time: Time):
        self._config = config
        self._websocket = websocket
        self._time = time
        self._backup_config: Optional[Dict[str, Any]] = None
        self._unavailable_reason: Optional[str] = None
        self._logged_unavailable = False
        self._completed_listeners: List[Callable[[], None]] = []
        websocket.onBackupEvent(self._handleEvent)

    async def refresh(self) -> None:
        """Reloads Home Assistant's backup configuration. Failures leave the add-on managing backups itself (in auto mode)."""
        if self._config.get(Setting.BACKUP_MODE) == BACKUP_MODE_ADDON and not self._config.get(Setting.USE_HOME_ASSISTANT_ENCRYPTION_KEY):
            # Nothing needs Home Assistant's configuration.
            return
        try:
            result = await self._websocket.call("backup/config/info")
            self._backup_config = result["config"]
            self._unavailable_reason = None
            self._logged_unavailable = False
        except Exception as e:
            self._backup_config = None
            self._unavailable_reason = e.detail if isinstance(e, HomeAssistantWebsocketError) else str(e)
            if not self._logged_unavailable:
                logger.info("Home Assistant's backup settings aren't available (%s), so the add-on will schedule backups itself", self._unavailable_reason)
                self._logged_unavailable = True

    @property
    def available(self) -> bool:
        return self._backup_config is not None

    @property
    def unavailableReason(self) -> Optional[str]:
        return self._unavailable_reason

    @property
    def schedulesBackups(self) -> bool:
        """True when Home Assistant, not the add-on, decides when new backups are created."""
        mode = self._config.get(Setting.BACKUP_MODE)
        if mode == BACKUP_MODE_ADDON:
            return False
        if mode == BACKUP_MODE_HOME_ASSISTANT:
            return True
        return self.available and self.hasSchedule

    @property
    def hasSchedule(self) -> bool:
        """True when Home Assistant's automatic backups are set up with a schedule."""
        if not self.available:
            return False
        return self._backup_config.get("automatic_backups_configured", False) and self._recurrence() != "never"

    @property
    def encryptionKey(self) -> Optional[str]:
        """The key Home Assistant encrypts its backups with, if one is set."""
        if not self.available:
            return None
        key = self._backup_config.get("create_backup", {}).get("password")
        return key if key else None

    @property
    def retentionDescription(self) -> str:
        retention = (self._backup_config or {}).get("retention", {}) or {}
        if retention.get("copies"):
            return "Home Assistant keeps the latest {0}".format(retention["copies"])
        if retention.get("days"):
            return "Home Assistant keeps backups for {0} days".format(retention["days"])
        return "Home Assistant keeps all of its automatic backups"

    def nextBackup(self) -> Optional[datetime]:
        """When Home Assistant plans to make its next automatic backup."""
        if not self.available:
            return None
        return self._parse(self._backup_config.get("next_automatic_backup"))

    def lastCompletedBackup(self) -> Optional[datetime]:
        if not self.available:
            return None
        return self._parse(self._backup_config.get("last_completed_automatic_backup"))

    def backupDueBy(self) -> Optional[datetime]:
        """
        The latest time a new automatic backup should exist by, if Home Assistant's schedule is working.
        Unlike nextBackup(), this doesn't move forward when a scheduled backup fails, so it can be used
        to notice when backups have gone stale.
        """
        if not self.hasSchedule:
            return None
        last = self.lastCompletedBackup()
        gap = self._longestScheduleGap()
        if last is None or gap is None:
            return self.nextBackup()
        return last + gap

    async def createBackup(self) -> str:
        """Asks Home Assistant to make a backup using its automatic backup settings. Returns the backup job ID."""
        result = await self._websocket.call("backup/generate_with_automatic_settings")
        return result.get("backup_job_id", "")

    def onBackupCompleted(self, listener: Callable[[], None]) -> None:
        self._completed_listeners.append(listener)

    def _handleEvent(self, event: Dict[str, Any]) -> None:
        if event.get("manager_state") == "create_backup" and event.get("state") == "completed":
            for listener in self._completed_listeners:
                listener()

    def _recurrence(self) -> str:
        return (self._backup_config.get("schedule", {}) or {}).get("recurrence", "never")

    def _longestScheduleGap(self) -> Optional[timedelta]:
        recurrence = self._recurrence()
        if recurrence == "daily":
            return timedelta(days=1)
        if recurrence != "custom_days":
            return None
        days = sorted({WEEKDAYS.index(day) for day in self._backup_config.get("schedule", {}).get("days", []) if day in WEEKDAYS})
        if len(days) == 0:
            return None
        gaps = [later - earlier for earlier, later in zip(days, days[1:])]
        gaps.append(days[0] + 7 - days[-1])
        return timedelta(days=max(gaps))

    def _parse(self, value) -> Optional[datetime]:
        if not value:
            return None
        try:
            return self._time.parse(value)
        except Exception:
            return None

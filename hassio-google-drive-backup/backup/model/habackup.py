from typing import Any, Dict

from backup.const import SOURCE_HA
from backup.exceptions import ensureKey
from backup.time import Time
from .backups import AbstractBackup
from backup.logger import getLogger
from backup.util import DataCache, KEY_I_MADE_THIS, KEY_IGNORE, KEY_NOTE
from backup.config import Config, Setting

logger = getLogger(__name__)

HA_KEY_TEXT = "Home Assistant's backup metadata"


def _parseSize(data: Dict[str, Any]) -> float:
    # Newer supervisors report an exact byte count, older ones only report megabytes.
    if data.get("size_bytes") is not None:
        return float(data["size_bytes"])
    if data.get("size") is not None:
        return float(data["size"]) * 1024 * 1024
    # Supervisors that support multiple backup locations may only report size per-location.
    for attributes in (data.get("location_attributes") or {}).values():
        if attributes.get("size_bytes") is not None:
            return float(attributes["size_bytes"])
    return float(ensureKey("size", data, HA_KEY_TEXT)) * 1024 * 1024


def _parseProtected(data: Dict[str, Any]) -> bool:
    if data.get("protected") is not None:
        return data["protected"]
    location_attributes = data.get("location_attributes") or {}
    if len(location_attributes) > 0:
        return any(attributes.get("protected", False) for attributes in location_attributes.values())
    return ensureKey('protected', data, HA_KEY_TEXT)


class HABackup(AbstractBackup):
    """
    Represents a Home Assistant backup stored locally in Home Assistant
    """

    def __init__(self, data: Dict[str, Any], data_cache: DataCache, config: Config, retained=False):
        super().__init__(
            name=ensureKey('name', data, HA_KEY_TEXT),
            slug=ensureKey('slug', data, HA_KEY_TEXT),
            date=Time.parse(ensureKey('date', data, HA_KEY_TEXT)),
            size=_parseSize(data),
            source=SOURCE_HA,
            backupType=ensureKey('type', data, HA_KEY_TEXT),
            version=ensureKey('homeassistant', data, HA_KEY_TEXT),
            protected=_parseProtected(data),
            retained=retained,
            uploadable=True,
            details=data,
            pending=False)
        self._data_cache = data_cache
        self._config = config

    def madeByTheAddon(self):
        return self._data_cache.backup(self.slug()).get(KEY_I_MADE_THIS, False)

    def note(self):
        parent = super().note()
        if parent is None:
            return self._data_cache.backup(self.slug()).get(KEY_NOTE, None)
        else:
            return parent

    def ignore(self):
        override = self._data_cache.backup(self.slug()).get(KEY_IGNORE, None)
        if override is not None:
            return override
        if self.madeByTheAddon():
            return False
        if self._config.get(Setting.IGNORE_OTHER_BACKUPS):
            return True
        archive_count = len(self.details().get("addons", [])) + len(self.details().get("folders", []))
        if self.details().get("homeassistant", None) is not None:
            # Supervisor backup query API doesn't quite match the create API, if the HA config folder
            # is present in a backup then the Home Assistant version is present in its details
            archive_count += 1
        if archive_count == 1 and self._config.get(Setting.IGNORE_UPGRADE_BACKUPS):
            return True
        return super().ignore()

    def __str__(self) -> str:
        return "<HA: {0} Name: {1} {2}>".format(self.slug(), self.name(), self.date().isoformat())

    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def __repr__(self) -> str:
        return self.__str__()

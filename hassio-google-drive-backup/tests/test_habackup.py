from backup.config import Config
from backup.model import HABackup
from backup.util import DataCache


def makeInfo(**kwargs):
    info = {
        "slug": "someslug",
        "name": "Some Backup",
        "date": "1985-12-06T05:00:00+00:00",
        "type": "full",
        "homeassistant": "2026.9.0",
        "folders": [],
        "addons": [],
    }
    info.update(kwargs)
    return info


def test_legacy_size_and_protected(config: Config, data_cache: DataCache):
    backup = HABackup(makeInfo(size=2.0, protected=True), data_cache, config)
    assert backup.size() == 2 * 1024 * 1024
    assert backup.protected()


def test_size_bytes_preferred(config: Config, data_cache: DataCache):
    backup = HABackup(makeInfo(size=2.0, size_bytes=1234567, protected=False), data_cache, config)
    assert backup.size() == 1234567
    assert not backup.protected()


def test_location_attributes(config: Config, data_cache: DataCache):
    info = makeInfo(
        locations=[None, "nas"],
        location_attributes={
            ".local": {"protected": False, "size_bytes": 4321},
            "nas": {"protected": True, "size_bytes": 4321},
        })
    backup = HABackup(info, data_cache, config)
    assert backup.size() == 4321
    assert backup.protected()

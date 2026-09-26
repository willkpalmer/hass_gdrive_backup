import logging
import re

import pytest

from backup.config import Config, Setting
from backup.ha import HaLogForwarder
from backup.logger import CONSOLE, FORWARD, HISTORY, appLoggerName, getLogger
from dev.request_interceptor import RequestInterceptor
from dev.simulated_supervisor import SimulatedSupervisor
from .faketime import FakeTime

# The line format Log Doctor (and Home Assistant) parse
HA_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) "
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL) "
    r"\((?P<thread>[^)]*)\) "
    r"\[(?P<logger>[^\]]*)\] "
    r"(?P<message>.*)$"
)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
URL_MATCH_SYSTEM_LOG = "^/core/api/services/system_log/write$"


@pytest.fixture
def forwarder(injector, config: Config):
    forwarder = injector.get(HaLogForwarder)
    FORWARD.pending.clear()
    FORWARD.enabled = True
    yield forwarder
    FORWARD.enabled = False
    FORWARD.pending.clear()


def test_logger_names():
    assert appLoggerName("backup.drive.drivesource") == "hass_gdrive_backup.drive.drivesource"
    assert appLoggerName("backup") == "hass_gdrive_backup"
    assert appLoggerName("dev.simulationserver") == "hass_gdrive_backup.dev.simulationserver"
    assert appLoggerName("hass_gdrive_backup.drive") == "hass_gdrive_backup.drive"
    assert getLogger("backup.ha.hasource").name == "hass_gdrive_backup.ha.hasource"


@pytest.mark.parametrize("handler", [CONSOLE, HISTORY])
def test_line_format_matches_home_assistant(handler):
    record = logging.LogRecord("hass_gdrive_backup.drive.drivesource", logging.ERROR, __file__, 1, "Upload failed", None, None)
    line = ANSI_RE.sub("", handler.format(record))
    match = HA_LINE_RE.match(line)
    assert match is not None, line
    assert match.group("level") == "ERROR"
    assert match.group("logger") == "hass_gdrive_backup.drive.drivesource"
    assert match.group("message") == "Upload failed"


@pytest.mark.asyncio
async def test_forwards_warnings_to_home_assistant(forwarder: HaLogForwarder, supervisor: SimulatedSupervisor, server):
    log = getLogger("backup.drive.drivesource")
    log.info("Uploading")
    log.warning("Upload slow")
    log.error("Upload failed")
    await forwarder.flush()
    assert supervisor.getSystemLog() == [
        {"message": "Upload slow", "level": "warning", "logger": "hass_gdrive_backup.drive.drivesource"},
        {"message": "Upload failed", "level": "error", "logger": "hass_gdrive_backup.drive.drivesource"},
    ]


@pytest.mark.asyncio
async def test_repeats_are_limited(forwarder: HaLogForwarder, supervisor: SimulatedSupervisor, server, time: FakeTime):
    log = getLogger("backup.ha.hasource")
    log.error("Backup failed")
    log.error("Backup failed")
    await forwarder.flush()
    assert len(supervisor.getSystemLog()) == 1

    time.advance(minutes=16)
    log.error("Backup failed")
    await forwarder.flush()
    assert len(supervisor.getSystemLog()) == 2


@pytest.mark.asyncio
async def test_kept_while_home_assistant_is_down(forwarder: HaLogForwarder, supervisor: SimulatedSupervisor, server, interceptor: RequestInterceptor):
    interceptor.setError(URL_MATCH_SYSTEM_LOG, 502)
    getLogger("backup.ha.hasource").error("Backup failed")
    await forwarder.flush()
    assert supervisor.getSystemLog() == []
    assert len(FORWARD.pending) == 1

    interceptor.clear()
    await forwarder.flush()
    assert len(supervisor.getSystemLog()) == 1


@pytest.mark.asyncio
async def test_can_be_turned_off(forwarder: HaLogForwarder, supervisor: SimulatedSupervisor, server, config: Config):
    config.override(Setting.LOG_TO_HOME_ASSISTANT, False)
    forwarder._updateEnabled()
    getLogger("backup.ha.hasource").error("Backup failed")
    await forwarder.flush()
    assert supervisor.getSystemLog() == []

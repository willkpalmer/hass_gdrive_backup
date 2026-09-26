import logging
from collections import deque
from logging import LogRecord, Formatter, ERROR
from traceback import TracebackException
from colorlog import ColoredFormatter
from os.path import join, abspath

HISTORY_SIZE = 1000

# Every logger this app creates is named under this prefix (e.g. "hass_gdrive_backup.drive.drivesource"),
# so its messages can be told apart from other add-ons and integrations in any log. See LOGGING.md.
LOGGER_PREFIX = "hass_gdrive_backup"

# The same line format as Home Assistant's own log, e.g.
# 2026-09-26 14:26:31.123 ERROR (MainThread) [hass_gdrive_backup.drive.drivesource] Something broke
LINE_FORMAT = '%(asctime)s.%(msecs)03d %(levelname)s (%(threadName)s) [%(name)s] %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
PATH_BASE = abspath(join(__file__, "..", ".."))

logging.addLevelName(5, "TRACE")
logging.TRACE = 5


class HistoryHandler(logging.Handler):
    def __init__(self):
        super(HistoryHandler, self).__init__()
        self.history = [None] * HISTORY_SIZE
        self.history_index = 0

    def reset(self):
        self.history = [None] * HISTORY_SIZE
        self.history_index = 0

    def emit(self, record: LogRecord):
        self.history[self.history_index % HISTORY_SIZE] = record
        self.history_index += 1

    def getHistory(self, start=0, html=False):
        end = self.history_index
        if end - start >= HISTORY_SIZE:
            start = end - HISTORY_SIZE
        for x in range(start, end):
            item = self.history[x % HISTORY_SIZE]
            if html:
                if item.levelno == logging.WARN:
                    style = "console-warning"
                elif item.levelno == logging.ERROR:
                    style = "console-error"
                elif item.levelno == logging.DEBUG:
                    style = "console-debug"
                elif item.levelno == logging.CRITICAL:
                    style = "console-critical"
                elif item.levelno == logging.FATAL:
                    style = "console-fatal"
                elif item.levelno == logging.WARNING:
                    style = "console-warning"
                elif item.levelno == logging.TRACE:
                    style = "console-trace"
                else:
                    style = "console-default"
                line = "<span class='" + style + \
                    "'>" + self.format(item) + "</span>"
                yield (x + 1, line)
            else:
                yield (x + 1, self.format(item))

    def getLast(self) -> LogRecord:
        return self.history[(self.history_index - 1) % HISTORY_SIZE]


CONSOLE = logging.StreamHandler()
CONSOLE.setLevel(logging.INFO)
formatter_color = ColoredFormatter(
    '%(log_color)s' + LINE_FORMAT + '%(reset)s',
    datefmt=DATE_FORMAT,
    reset=True,
    log_colors={
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red",
        "TRACE": "white",
    },
)
CONSOLE.setFormatter(formatter_color)

HISTORY = HistoryHandler()
HISTORY.setLevel(logging.DEBUG)
HISTORY.setFormatter(Formatter(LINE_FORMAT, DATE_FORMAT))


class ForwardingHandler(logging.Handler):
    """
    Holds warnings and errors until HaLogForwarder sends them to Home Assistant's own log. Records can
    come from any thread, so they're only queued here.
    """

    def __init__(self):
        super().__init__(logging.WARNING)
        self.pending = deque(maxlen=100)
        self.enabled = False

    def emit(self, record: LogRecord):
        if self.enabled and not getattr(record, "skip_forwarding", False):
            self.pending.append(record)


FORWARD = ForwardingHandler()


class StandardLogger(logging.Logger):
    def __init__(self, name):
        super().__init__(name)
        self.setLevel(logging.TRACE)
        self.addHandler(CONSOLE)
        self.addHandler(HISTORY)
        self.addHandler(FORWARD)

    def trace(self, msg, *args, **kwargs):
        self.log(logging.TRACE, msg, *args, **kwargs)

    def printException(self, ex: Exception, level=ERROR):
        self.log(level, self.formatException(ex))

    def formatException(self, e: Exception) -> str:
        trace = None
        if (hasattr(e, "__traceback__")):
            trace = e.__traceback__
        tbe = TracebackException(type(e), e, trace, limit=None)
        lines = list(self._format(tbe))
        return '\n%s' % ''.join(lines)

    def _format(self, tbe):
        if (tbe.__context__ is not None and not tbe.__suppress_context__):
            yield from self._format(tbe.__context__)
            yield "Whose handling caused:\n"
        is_addon, stack = self._formatStack(tbe)
        yield from stack
        yield from tbe.format_exception_only()

    def _formatStack(self, tbe):
        _RECURSIVE_CUTOFF = 3
        result = []
        last_file = None
        last_line = None
        last_name = None
        count = 0
        is_addon = False
        buffer = []
        for frame in tbe.stack:
            line_internal = True
            if (last_file is None or last_file != frame.filename or last_line is None or last_line != frame.lineno or last_name is None or last_name != frame.name):
                if count > _RECURSIVE_CUTOFF:
                    count -= _RECURSIVE_CUTOFF
                    result.append(
                        f'  [Previous line repeated {count} more '
                        f'time{"s" if count > 1 else ""}]\n'
                    )
                last_file = frame.filename
                last_line = frame.lineno
                last_name = frame.name
                count = 0
            count += 1
            if count > _RECURSIVE_CUTOFF:
                continue
            fileName = frame.filename
            pos = fileName.rfind(PATH_BASE)
            if pos >= 0:
                is_addon = True
                line_internal = False
                fileName = "addon" + \
                    fileName[pos + len(PATH_BASE):]

            pos = fileName.rfind("site-packages")
            if pos > 0:
                fileName = fileName[pos - 1:]

            pos = fileName.rfind("python3.7")
            if pos > 0:
                fileName = fileName[pos - 1:]
                pass
            line = '  {}:{} ({})\n'.format(fileName, frame.lineno, frame.name)
            if line_internal:
                buffer.append(line)
            else:
                result.extend(self._compressFrames(buffer))
                buffer = []
                result.append(line)
        if count > _RECURSIVE_CUTOFF:
            count -= _RECURSIVE_CUTOFF
            result.append(
                f'  [Previous line repeated {count} more '
                f'time{"s" if count > 1 else ""}]\n'
            )
        result.extend(self._compressFrames(buffer))
        return is_addon, result

    def overrideLevel(self, console, history):
        CONSOLE.setLevel(console)
        HISTORY.setLevel(history)

    def _compressFrames(self, buffer):
        if len(buffer) > 1:
            yield buffer[0]
            if len(buffer) == 3:
                yield buffer[1]
            elif len(buffer) > 2:
                yield "  [{} hidden frames]\n".format(len(buffer) - 2)
            yield buffer[len(buffer) - 1]
        elif len(buffer) > 0:
            yield buffer[len(buffer) - 1]
            pass


def appLoggerName(name: str) -> str:
    """Puts a module's logger name under LOGGER_PREFIX, e.g. "backup.drive.drivesource" -> "hass_gdrive_backup.drive.drivesource"."""
    if name == LOGGER_PREFIX or name.startswith(LOGGER_PREFIX + "."):
        return name
    if name == "backup" or name.startswith("backup."):
        return LOGGER_PREFIX + name[len("backup"):]
    return LOGGER_PREFIX + "." + name


def getLogger(name):
    return StandardLogger(appLoggerName(name))


def getHistory(index, html):
    return HISTORY.getHistory(index, html)


def getLast() -> LogRecord:
    return HISTORY.getLast()


def reset() -> None:
    return HISTORY.reset()


class TraceLogger(StandardLogger):
    def __init__(self, name):
        super().__init__(name)
        self.setLevel(logging.TRACE)

    def log(self, lvl, msg, *args, **kwargs):
        super().log(logging.TRACE, msg, *args, **kwargs)

    def info(self, *args, **kwargs):
        super().log(logging.TRACE, *args, **kwargs)

    def error(self, *args, **kwargs):
        super().log(logging.TRACE, *args, **kwargs)

    def warn(self, *args, **kwargs):
        super().log(logging.TRACE, *args, **kwargs)

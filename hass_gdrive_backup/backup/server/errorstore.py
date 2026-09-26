from .cloudlogger import CloudLogger
from injector import inject, singleton


@singleton
class ErrorStore():
    """
    Keeps error reports sent by add-on installs. They're written to the server's log, and the most
    recent one is kept in memory.
    """
    @inject
    def __init__(self, logger: CloudLogger):
        self._logger = logger
        self.last_error = None

    def store(self, error_data):
        self._logger.log_struct({"error_report": error_data})
        self.last_error = error_data

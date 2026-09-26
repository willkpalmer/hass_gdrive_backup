import json
from backup.logger import StandardLogger
from injector import inject, singleton


@singleton
class CloudLogger(StandardLogger):
    """
    Logs structured data as single-line JSON on stdout. Container hosts (Cloud Run, Fly.io, Docker)
    collect stdout, and Cloud Run parses JSON lines into structured log entries.
    """
    @inject
    def __init__(self):
        super().__init__(__name__)

    def log_struct(self, data):
        print(json.dumps(data, default=str), flush=True)

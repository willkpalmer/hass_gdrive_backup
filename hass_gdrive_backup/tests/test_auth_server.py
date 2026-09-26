import pytest
from types import SimpleNamespace

from backup.config import Config, Setting
from backup.creds import Creds
from backup.drive import DriveSource
from backup.server import Server
from backup.server.__main__ import ServerModule
from .conftest import ReaderHelper
from .faketime import FakeTime


def test_auth_server_url_used_for_both_endpoints():
    config = Config()
    assert config.get(Setting.AUTHORIZATION_HOST) == Setting.AUTHORIZATION_HOST.default()

    config = Config({Setting.AUTH_SERVER_URL: "https://auth.example.com/"})
    assert config.get(Setting.AUTHORIZATION_HOST) == "https://auth.example.com"
    assert config.get(Setting.TOKEN_SERVER_HOSTS) == "https://auth.example.com"
    assert [str(url) for url in config.getTokenServers("/drive/refresh")] == ["https://auth.example.com/drive/refresh"]


def test_explicit_hosts_win_over_auth_server_url():
    config = Config({
        Setting.AUTH_SERVER_URL: "https://auth.example.com",
        Setting.TOKEN_SERVER_HOSTS: "https://token.example.com",
    })
    assert config.get(Setting.AUTHORIZATION_HOST) == "https://auth.example.com"
    assert config.get(Setting.TOKEN_SERVER_HOSTS) == "https://token.example.com"


def test_saving_config_keeps_auth_server_derived():
    """Saving settings from the web UI must keep auth_server_url, not freeze the hosts derived from it."""
    config = Config({Setting.AUTH_SERVER_URL: "https://auth.example.com"})
    validated, _ = config.validate({Setting.MAX_BACKUPS_IN_HA.value: 5})
    assert validated[Setting.AUTH_SERVER_URL] == "https://auth.example.com"
    assert Setting.TOKEN_SERVER_HOSTS not in validated
    assert Setting.AUTHORIZATION_HOST not in validated


def test_custom_creds_detected_by_secret(drive: DriveSource, time: FakeTime):
    drive.drivebackend.creds = Creds(time, "any-client-id", None, "access", "refresh")
    assert not drive.isCustomCreds()
    drive.drivebackend.creds = Creds(time, "any-client-id", None, "access", "refresh", secret="secret")
    assert drive.isCustomCreds()


def test_server_requires_configuration():
    # Only the configuration matters here, so skip building the server's HTTP session.
    server = SimpleNamespace(config=Config())
    assert Server.missingConfiguration(server) == ["DEFAULT_DRIVE_CLIENT_ID", "DEFAULT_DRIVE_CLIENT_SECRET", "AUTHORIZATION_HOST"]

    config = Config({
        Setting.DEFAULT_DRIVE_CLIENT_ID: "id",
        Setting.DEFAULT_DRIVE_CLIENT_SECRET: "secret",
        Setting.AUTHORIZATION_HOST: "https://auth.example.com",
    })
    assert Server.missingConfiguration(SimpleNamespace(config=config)) == []


def test_server_reads_environment(monkeypatch):
    monkeypatch.setenv("DEFAULT_DRIVE_CLIENT_ID", "id")
    monkeypatch.setenv("AUTHORIZATION_HOST", "https://auth.example.com")
    monkeypatch.setenv("SERVER_CONTACT_EMAIL", "me@example.com")
    config = ServerModule().getConfig()
    assert config.get(Setting.DEFAULT_DRIVE_CLIENT_ID) == "id"
    assert config.get(Setting.AUTHORIZATION_HOST) == "https://auth.example.com"
    assert config.get(Setting.SERVER_CONTACT_EMAIL) == "me@example.com"


@pytest.mark.asyncio
async def test_policy_pages_use_auth_server(reader: ReaderHelper, config: Config):
    config.override(Setting.AUTHORIZATION_HOST, "https://auth.example.com")
    config.override(Setting.SERVER_CONTACT_EMAIL, "me@example.com")
    for page in ["pp", "tos"]:
        html = await reader.get(page)
        assert "https://auth.example.com" in html
        assert "habackup" not in html
    assert "me@example.com" in await reader.get("pp")

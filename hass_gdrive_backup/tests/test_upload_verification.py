import hashlib

import pytest

from backup.drive import DriveSource
from backup.drive.driverequests import UploadHasher
from backup.exceptions import UploadVerificationFailed, GoogleInternalError
from dev.simulated_google import SimulatedGoogle, URL_MATCH_UPLOAD_PROGRESS
from dev.request_interceptor import RequestInterceptor
from .conftest import BackupHelper


def test_hasher_follows_seeks():
    data = bytes(range(256)) * 10
    hasher = UploadHasher()
    hasher.update(0, data[:1000])
    # Drive only accepted the first 600 bytes, so the upload seeks back and re-sends from there
    hasher.update(600, data[600:1500])
    hasher.update(1500, data[1500:])
    assert hasher.hexdigest() == hashlib.md5(data).hexdigest()


def test_hasher_gives_up_on_gaps():
    data = bytes(range(256)) * 10
    hasher = UploadHasher()
    # Resuming an upload skips bytes sent by an earlier attempt
    hasher.update(1000, data[1000:])
    assert hasher.hexdigest() is None


@pytest.mark.asyncio
async def test_upload_is_verified(drive: DriveSource, backup_helper: BackupHelper, google: SimulatedGoogle):
    from_backup, data = await backup_helper.createFile()
    uploaded = await drive.save(from_backup, data)
    assert uploaded.verified()

    # The verification is stored with the file in Google Drive
    stored = (await drive.get())[from_backup.slug()]
    assert stored.verified()
    assert google.items[stored.id()]['appProperties']['verified'] == "md5"


@pytest.mark.asyncio
async def test_corrupt_upload_is_deleted(drive: DriveSource, backup_helper: BackupHelper, google: SimulatedGoogle):
    google.corrupt_uploads = True
    from_backup, data = await backup_helper.createFile()
    with pytest.raises(UploadVerificationFailed):
        await drive.save(from_backup, data)
    assert len(await drive.get()) == 0

    google.corrupt_uploads = False
    data.position(0)
    assert (await drive.save(from_backup, data)).verified()


@pytest.mark.asyncio
async def test_resumed_upload_isnt_verified(drive: DriveSource, backup_helper: BackupHelper, interceptor: RequestInterceptor):
    from_backup, data = await backup_helper.createFile()
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, fail_after=1, status=500)
    with pytest.raises(GoogleInternalError):
        await drive.save(from_backup, data)

    interceptor.clear()
    data.position(0)
    uploaded = await drive.save(from_backup, data)
    assert not uploaded.verified()

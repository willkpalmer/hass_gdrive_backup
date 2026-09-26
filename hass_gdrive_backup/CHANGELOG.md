## v0.1.1 [2026-09-26]

- Fixed a resource leak: the add-on's DNS resolvers were never closed, and each one keeps a file watch open. This also made the test suite fail once enough had accumulated.
- Removed leftover deployment scripts, staging workflows and Heroku config from the original project.

## v0.1.0 [2026-09-26]

First release of `hass_gdrive_backup`, a new add-on forked from [sabeechen/hassio-google-drive-backup](https://github.com/sabeechen/hassio-google-drive-backup) v0.112.1. It installs as a separate add-on (slug `hass_gdrive_backup`) and can't be upgraded to from the original, so install it fresh and authenticate with Google Drive again.

Changes from the original add-on:

- Updated for current Home Assistant OS / Supervisor releases:
  - The add-on manifest is now `config.yaml`, and the repository manifest is now `repository.yaml`.
  - Added `build.yaml`, building on Home Assistant's current `base-python` images (Python 3.13, Alpine 3.24).
  - Supports `aarch64` and `amd64` only. Home Assistant stopped supporting `armhf`, `armv7` and `i386` in 2025.12.
  - Uses the current `map` format (`homeassistant_config` in place of the deprecated `config` folder).
  - The add-on is built locally by the Supervisor instead of downloading a prebuilt image.
- Handles backup metadata from Supervisors that support multiple backup locations (`size_bytes`, `location_attributes`).
- Removed unused dependencies (`oauth2client`, Google API client libraries, `aiofile(s)`) and a workaround for very old `python-dateutil` versions.
- Fixed a Python version-specific path that broke the add-on on base images newer than Python 3.11.
- Links in the docs and web UI point to this repository.
- A GitHub Release (`v<version>`) is created automatically whenever `master` carries a new version.
- Google Drive sign-in still goes through the original add-on's hosted token server, which picks its auth protocol from the add-on version. The add-on reports the upstream version it was forked from (0.112.1) to that server, so restarting at 0.1.0 doesn't break sign-in.
- Removed notices meant for people upgrading from old versions of the original add-on, which can't happen with this one.

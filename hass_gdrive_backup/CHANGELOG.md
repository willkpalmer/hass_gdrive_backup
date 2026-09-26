## v0.4.0 [2026-09-26]

- The add-on now works with Home Assistant's own backup system (Settings > System > Backups). With the new `backup_mode` option (default `auto`), when you've set up automatic backups in Home Assistant, Home Assistant decides when backups are made, what goes in them, their encryption and how many stay on the device. The add-on uploads them to Google Drive as soon as they finish, keeps its own Google Drive retention (including generational backups), and still warns you if they stop happening. Set `backup_mode: addon` to keep the add-on's own schedule.
- "Backup now" asks Home Assistant for a backup with its automatic backup settings when Home Assistant is scheduling.
- Backups the add-on makes itself are now encrypted with Home Assistant's backup encryption key when no backup password is set (`use_home_assistant_encryption_key`).

## v0.3.0 [2026-09-26]

- Added the `auth_server_url` option for using your own Google Drive auth server. See [AUTH_SERVER.md](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/AUTH_SERVER.md) for setting one up on Google Cloud Run or any Docker host.
- The auth server is now self-hostable: it's configured entirely through environment variables, logs to stdout instead of Google Cloud Logging/Firestore, serves its own privacy policy and terms pages, and refuses to start without its required settings.
- The privacy policy and terms pages now show the auth server you actually use.

## v0.2.0 [2026-09-26]

- Removed the "Stop Addons" feature (and its "disable watchdog" option). The Supervisor now tells add-ons when they're being backed up, so stopping them first is no longer needed, and the feature often failed to restart add-ons afterward.

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

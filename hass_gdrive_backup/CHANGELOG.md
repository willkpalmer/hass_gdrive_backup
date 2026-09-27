## v0.11.1 [2026-09-27]

- Partial backups no longer ask Home Assistant to include the local add-ons folder (`addons/local`) when no local add-ons are installed. Home Assistant only creates that folder for local add-ons, so asking for it logged "Can't find backup folder addons/local" in the Supervisor's log.
- When a backup fails, the Supervisor log popup now shows the actual reason at the top, and notes that warnings like "Can't find backup folder" are usually harmless. Opening the popup again no longer repeats the log.

## v0.11.0 [2026-09-27]

- ESPHome backups now upload a new copy every time they're scheduled. Before, a scheduled ESPHome backup quietly uploaded nothing when the configurations hadn't changed since the last one, so it looked like it hadn't run.
- The ESPHome backup folder is chosen the same way as the main backup folder: in the settings, turn on "Manually specify the ESPHome backup folder" and use "Choose Folder" to pick one and paste its ID (new option `esphome_specify_folder`). Otherwise the add-on still creates an "ESPHome Backups" folder. The status line links to the folder being used.
- ESPHome backup errors now show their message in the web UI and log.

## v0.10.0 [2026-09-26]

- New, optional ESPHome configuration backups: the ESPHome add-on's device configurations (`/config/esphome`) can be backed up to their own Google Drive folder, either with each new Home Assistant backup or on their own schedule. They're verified after uploading, skipped when nothing has changed, and old ones are cleaned up. Turn them on with `esphome_backup` or in the web UI's settings, which also shows when they were last backed up and has a "Back up now" link.

## v0.9.2 [2026-09-26]

- Removed `build.yaml`, which the Supervisor now reports as deprecated. The Dockerfile names its own base image (Home Assistant's multi-arch Python image) and labels.

## v0.9.1 [2026-09-26]

- A cancelled sync is no longer logged as an error (or copied to Home Assistant's log). Saving settings now logs "Restarting the sync to apply new settings", and a sync interrupted by the add-on stopping or updating says so, instead of both reporting "Sync was cancelled by you". Cancelling with the button still shows in the web UI.

## v0.9.0 [2026-09-26]

- Log messages now use Home Assistant's log format, and every logger name starts with `hass_gdrive_backup`, so this app's backup messages are easy to find and filter in any log. See [LOGGING.md](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/LOGGING.md).
- Warnings and errors are also written to Home Assistant's own log (Settings > System > Logs), with repeats limited to once every 15 minutes. Turn this off with `log_to_home_assistant: false`.
- The add-on logs its name and version when it starts.

## v0.8.2 [2026-09-26]

- The add-on's maintainer is now listed as willkpalmer. The help dialog and bug reports point to this repository's GitHub issues instead of the original author's email.

## v0.8.1 [2026-09-26]

- Renamed the add-on to "GDrive Backup Utility". The slug and entity IDs are unchanged, so existing automations keep working.
- Replaced the long repository README and the add-on store's info page with short descriptions. The detailed guide and FAQ are now in [FAQ.md](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/FAQ.md).

## v0.8.0 [2026-09-26]

- Backups can now be restored straight from the add-on: click "Restore" on any backup, including ones only in Google Drive (which are copied back into Home Assistant first). Restore everything, or choose the Home Assistant configuration, folders and add-ons to restore. Encrypted backups use your backup password or Home Assistant's backup encryption key unless you enter one.

## v0.7.0 [2026-09-26]

- Added the `notify_service` option to also send backup problems through a notify service, such as your phone via the Home Assistant companion app, with a follow-up when backups are working again. It's also in the web UI's settings.

## v0.6.0 [2026-09-26]

- The add-on's sensors are now real Home Assistant entities when an MQTT broker is set up (for example the Mosquitto add-on). They're created through MQTT discovery under a "Google Drive Backup" device, can be renamed and customized, keep their values across Home Assistant restarts, and include new "Last backup", "Last upload", "Next backup" and backup count sensors. Without a broker (or with `mqtt_discovery: false`) the add-on sets its two sensors through Home Assistant's API as before.

## v0.5.0 [2026-09-26]

- Uploads to Google Drive are now verified: the add-on checksums each backup as it uploads it and compares that with the checksum Google Drive reports. Verified backups get a new icon in the web UI. If they don't match, the copy in Google Drive is deleted and the upload is retried, instead of keeping a backup that might not restore.

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

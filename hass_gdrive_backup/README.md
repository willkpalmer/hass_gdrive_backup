# GDrive Backup Utility

Keeps copies of your Home Assistant backups in Google Drive, so you can recover your setup even if the device running Home Assistant fails.

- Backs up on a schedule, using Home Assistant's automatic backups or its own.
- Uploads each backup to Google Drive and verifies it arrived intact.
- Cleans up old backups in Home Assistant and Google Drive.
- Restores any backup in one step, even ones only in Google Drive.
- Warns you through sensors, notifications or your phone when backups stop.

After installing, start the add-on and open its web UI. It walks you through connecting Google Drive.

See the Documentation tab for every option, or the [guide and FAQ](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/FAQ.md).

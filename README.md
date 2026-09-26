# GDrive Backup Utility

A Home Assistant add-on that keeps copies of your Home Assistant backups in Google Drive, so you can recover your setup even if the device running Home Assistant fails.

## What it does

- **Backs up on a schedule.** Use the automatic backups you've set up in Home Assistant, or let the add-on make its own.
- **Uploads to Google Drive.** Each backup is copied to a folder in your Drive and checked against Google's checksum, so you know it arrived intact.
- **Cleans up old backups.** Choose how many to keep in Home Assistant and in Google Drive, or keep daily, weekly, monthly and yearly backups for longer.
- **Restores in one step.** Restore any backup from the add-on, including ones that are only in Google Drive.
- **Tells you when something's wrong.** Sensors, Home Assistant notifications, and optional messages to your phone.
- **Encrypts backups.** It uses your Home Assistant backup encryption key, or a password you choose.

## Install

1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
2. Open the menu in the top right, choose **Repositories**, and add `https://github.com/willkpalmer/hass_gdrive_backup`.
3. Find **GDrive Backup Utility** in the store, install it, then start it and open its web UI.
4. Follow the web UI to connect your Google Drive.

## More information

- [Configuration options](hass_gdrive_backup/DOCS.md)
- [Guide and FAQ](FAQ.md)
- [Running your own sign-in server](AUTH_SERVER.md)
- [Changelog](hass_gdrive_backup/CHANGELOG.md)

This is a fork of [sabeechen/hassio-google-drive-backup](https://github.com/sabeechen/hassio-google-drive-backup), updated for current versions of Home Assistant. It's installed separately from the original add-on, and backups made with either can be restored with either.

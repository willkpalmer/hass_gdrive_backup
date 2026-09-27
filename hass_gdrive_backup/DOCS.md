# GDrive Backup Utility

## Installation

To install the add-on, first follow the [installation steps on GitHub](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/FAQ.md#detailed-install-instructions).

## Configuration

_Note_: The configuration can be changed easily by starting the add-on and clicking `Settings` in the web UI.
The UI explains what each setting is and you don't need to modify anything before clicking `Start`.
If you would still prefer to modify the settings in yaml, the options are detailed below.

### Add-on configuration example
Don't use this directly, the addon has a lot of configuration options that most users don't need or want:

```yaml
# Keep 10 backups in Home Assistant
max_backups_in_ha: 10

# Keep 10 backups in Google Drive
max_backups_in_google_drive: 10

# Create backups in Home Assistant on network storage 
backup_location: my_nfs_share

# Ignore backups the add-on hasn't created
ignore_other_backups: True

# Ignore backups that look like they were created by Home Assistant automatic backup option during upgrades
ignore_upgrade_backups: True

# Automatically delete "ignored" snapshots after this many days
delete_ignored_after_days: 7

# Take a backup every 3 days
days_between_backups: 3

# Create backups at 1:30pm exactly
backup_time_of_day: "13:30"

# Delete backups from Home Assistant immediately after uploading them to Google Drive
delete_after_upload: True

# Manually specify the backup folder used in Google Drive
specify_backup_folder: true

# Use a dark and red theme
background_color: "#242424"
accent_color: "#7D0034"

# Use a password for backup archives.  Use "!secret secret_name" to use a password form your secrets file
backup_password: "super_secret"

# Create backup names like 'Full Backup HA 0.92.0'
backup_name: "{type} Backup HA {version_ha}"

# Keep a backup once every day for 3 days and once a week for 4 weeks
generational_days: 3
generational_weeks: 4

# Create partial backups with no folders and no configurator add-on
exclude_folders: "homeassistant,ssl,share,addons/local,media"
exclude_addons: "core_configurator"

# Turn off notifications and staleness sensor
enable_backup_stale_sensor: false
notify_for_stale_backups: false

# Enable server directly on port 1627
expose_extra_server: true

# Allow sending error reports
send_error_reports: true

# Delete backups after they're uploaded to Google Drive
delete_after_upload: true
```

### Option: `backup_mode` (default: `auto`)

Decides who schedules new backups.

- `home_assistant`: Home Assistant's own automatic backups (**Settings > System > Backups**) decide when backups are made, what goes in them, how they're encrypted and how many stay on the device. The add-on uploads them to Google Drive as soon as they finish, applies its own Google Drive retention (including generational backups), and warns you if they stop happening. "Backup now" in the add-on asks Home Assistant for a backup with those same settings. `days_between_backups`, `backup_time_of_day` and `max_backups_in_ha` are ignored.
- `addon`: the add-on makes backups on its own schedule, as configured by the options below.
- `auto`: `home_assistant` when automatic backups are set up with a schedule in Home Assistant, otherwise `addon`.

### Option: `max_backups_in_ha` (default: 4)

The number of backups the add-on will allow Home Assistant to store locally before old ones are deleted. Ignored when Home Assistant schedules backups (see `backup_mode`).

### Option: `max_backups_in_google_drive` (default: 4)

The number of backups the add-on will keep in Google Drive before old ones are deleted. Google Drive gives you 15GB of free storage (at the time of writing) so plan accordingly if you know how big your backups are.

### Option: `backup_location` (default: None)
The place where backups are created in Home Assistant before uploading to Google Drive.  Can be "local-disk" or the name of any backup network storage you've configured in Home Assistant.  Leave unspecified (the default) to have backups created in whatever Home Assistant uses as the default backup location. 

### Option: `ignore_other_backups` (default: False)
Make the addon ignore any backups it didn't directly create.  Any backup already uploaded to Google Drive will not be ignored until you delete it from Google Drive.

### Option: `ignore_upgrade_backups` (default: False)
Ignores backups that look like they were automatically created from updating an add-on or Home Assistant itself.  This will make the add-on ignore any partial backup that has only one add-on or folder in it.

### Option: `days_between_backups` (default: 3)

How often a new backup should be scheduled, eg `1` for daily and `7` for weekly.

### Option: `backup_time_of_day`

The time of day (local time) that new backups should be created in 24-hour ("HH:MM") format. When not specified backups are created at (roughly) the same time of day as the most recent backup.


### Options: `delete_after_upload` (default: False)

Deletes backups from Home Assistant immediately after uploading them to Google Drive.  This is useful if you have very limited space inside Home Assistant since you only need to have available space for a single backup locally.

### Option: `specify_backup_folder` (default: False)

When true, you must select the folder in Google Drive where backups are stored. Once you turn this on, restart the add-on and visit the Web-UI to be prompted to select the backup folder.

### Option: `background_color` and `accent_color`

The background and accent colors for the web UI. You can use this to make the UI fit in with whatever color scheme you use in Home Assistant. When unset, the interface matches Home Assistant's default blue/white style.

### Option: `backup_password`

When set, backups are created with a password. You can use a value from your secrets.yaml by prefixing the password with "!secret". You'll need to remember this password when restoring a backup.

> Example: Use a password for backup archives
>
> ```yaml
> backup_password: "super_secret"
> ```
>
> Example: Use a password from secrets.yaml
>
> ```yaml
> backup_password: "!secret backup_password"
> ```

### Option: `use_home_assistant_encryption_key` (default: True)

When `backup_password` isn't set, the backups the add-on makes are encrypted with Home Assistant's backup encryption key, the same key Home Assistant uses for its own backups and that's in your Home Assistant backup emergency kit. Set this to false to make unencrypted backups instead. If you later change the key in Home Assistant, older backups still need the key they were made with.

### Option: `backup_name` (default: "{type} Backup {year}-{month}-{day} {hr24}:{min}:{sec}")

Sets the name for new backups. Variable parameters of the form `{variable_name}` can be used to modify the name to your liking. A list of available variables is available [here](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/FAQ.md#can-i-give-backups-a-different-name).

### Option: `generational_*`

When set, older backups will be kept longer using a [generational backup scheme](https://en.wikipedia.org/wiki/Backup_rotation_scheme). See the [question here](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/FAQ.md#can-i-keep-older-backups-for-longer) for configuration options.

### Option: `exclude_folders`

When set, excludes the comma-separated list of folders by creating a partial backup.

### Option: `exclude_addons`

When set, excludes the comma-separated list of addons by creating a partial backup.

_Note_: Folders and add-ons must be identified by their "slug" name. It is recommended to use the `Settings` dialog within the add-on web UI to configure partial backups since these names are esoteric and hard to find.

### Option: `notify_service`

A notify service to also send backup problems to, such as `notify.mobile_app_my_phone` to get them on your phone through the Home Assistant companion app. You get one message when backups need attention and another when they're working again. Tapping the notification opens the add-on.

### ESPHome configuration backups

Backs up the ESPHome add-on's device configurations (`/config/esphome`) to their own Google Drive folder, separately from your Home Assistant backups. This makes it easy to get a single device's configuration back without restoring a whole backup. ESPHome's build cache (`.esphome`) isn't included, since ESPHome rebuilds it. Every scheduled ESPHome backup uploads a new copy, even when the configurations haven't changed. The web UI shows when they were last backed up, links to the folder, and has a "Back up now" link.

To choose the folder, open the add-on's settings, turn on "Back Up ESPHome Configuration", then "Manually specify the ESPHome backup folder", and use the "Choose Folder" button to pick a folder and paste its ID, just like the main backup folder. Otherwise the add-on creates an "ESPHome Backups" folder in your My Drive.

Each backup is a `.tar.gz` file. It includes ESPHome's `secrets.yaml` and isn't encrypted, so it's only as private as your Google Drive.

> Example: back up ESPHome configurations every night at 2am, keeping two weeks of them
>
> ```yaml
> esphome_backup: true
> esphome_schedule: own_schedule
> esphome_days_between_backups: 1
> esphome_backup_time_of_day: "02:00"
> esphome_max_backups_in_google_drive: 14
> ```

#### Option: `esphome_backup` (default: False)

Turns ESPHome configuration backups on.

#### Option: `esphome_specify_folder` (default: False)

Upload ESPHome backups into a Google Drive folder you choose in the settings (with the "Choose Folder" button), instead of one the add-on creates.

#### Option: `esphome_drive_folder` (default: "ESPHome Backups")

When `esphome_specify_folder` is off, the name of the folder the add-on creates at the top of your Drive. Changing the name starts a new folder; the old one is left as it is.

#### Option: `esphome_schedule` (default: `with_backups`)

`with_backups` backs up the ESPHome configurations each time a new Home Assistant backup is made, whether the add-on or Home Assistant made it. `own_schedule` uses the two options below instead.

#### Option: `esphome_days_between_backups` (default: 1)

With `own_schedule`, how many days apart ESPHome backups are. `0` stops scheduled ESPHome backups ("Back up now" still works).

#### Option: `esphome_backup_time_of_day`

With `own_schedule`, the time of day to back up, as `HH:MM` in 24-hour time. Leave it unset to back up that many days after the last one.

#### Option: `esphome_max_backups_in_google_drive` (default: 10)

How many ESPHome backups to keep in Google Drive. Older ones are deleted. `0` keeps them all.

### Option: `log_to_home_assistant` (default: True)

Also writes the add-on's warnings and errors to Home Assistant's own log (Settings > System > Logs), under logger names starting with `hass_gdrive_backup`. See [LOGGING.md](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/LOGGING.md) for the log format.

### Option: `mqtt_discovery` (default: True)

When an MQTT broker is set up in Home Assistant (for example the Mosquitto broker add-on with the MQTT integration), the add-on creates its sensors through MQTT discovery, grouped under a "GDrive Backup Utility" device:

- `binary_sensor.backups_stale`: on when backups have stopped being made or uploaded
- `sensor.backup_state`: `backed_up`, `waiting` or `error`, with details about every backup as attributes
- "Last backup", "Last upload" and "Next backup" timestamps
- "Backups in Home Assistant" and "Backups in Google Drive" counts

These are regular entities: you can rename them and change their settings in Home Assistant, and they keep their last value across restarts. When no MQTT broker is available, or this option is false, the add-on sets `binary_sensor.backups_stale` and `sensor.backup_state` through Home Assistant's API instead, as it always has; those can't be edited in the UI and are unavailable after Home Assistant restarts until the add-on updates them.

### Option: `enable_backup_stale_sensor` (default: True)

When false (and MQTT isn't used, see `mqtt_discovery`), the add-on will not publish the [binary_sensor.backups_stale](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/FAQ.md#how-will-i-know-this-will-be-there-when-i-need-it) stale sensor.

### Option: `enable_backup_state_sensor` (default: True)

When false (and MQTT isn't used, see `mqtt_discovery`), the add-on will not publish the [sensor.backup_state](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/FAQ.md#how-will-i-know-this-will-be-there-when-i-need-it) sensor.

### Option: `notify_for_stale_backups` (default: True)

When false, the add-on will send a [persistent notification](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/FAQ.md#how-will-i-know-this-will-be-there-when-i-need-it) in Home Assistant when backups are stale.

---

### Option: `auth_server_url`

The URL of your own auth server, such as `https://auth.example.com`. The add-on uses it to sign in to Google Drive and to refresh its access. After changing it, sign in to Google Drive again from the add-on's web UI. See [AUTH_SERVER.md](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/AUTH_SERVER.md) for how to run one.

### UI Server Options

The UI is available through Home Assistant [ingress](https://www.home-assistant.io/blog/2019/04/15/hassio-ingress/).

It can also be exposed through a web server on port `1627`, which you can map to an externally visible port from the add-on `Network` panel. You can configure a few more options to add SSL or require your Home Assistant username/password.

#### Option: `expose_extra_server` (default: False)

Expose the webserver on port `1627`. This is optional, as the add-on is already available with Home Assistant ingress.

#### Option: `require_login` (default: False)

When true, requires your home assistant username and password to access the Web UI.

#### Option: `use_ssl` (default: False)

When true, the Web UI exposed by `expose_extra_server` will be served over SSL (HTTPS).

#### Option: `certfile` (default: `/ssl/certfile.pem`)

Required when `use_ssl: True`. The path to your SSL key file

#### Option: `keyfile` (default: `/ssl/keyfile.pem`)

Required when `use_ssl: True`. The path to your SSL cert file.

#### Option: `verbose` (default: False)

If true, enable additional debug logging. Useful if you start seeing errors and need to file a bug with me.

#### Option: `send_error_reports` (default: False)

When true, the text of unexpected errors will be sent to a database maintained by the developer. This helps identify problems with new releases and provide better context messages when errors come up.

#### Option: `delete_after_upload` (default: False)

When true, backups are always deleted after they've been uploaded to Google Drive.  'max_backups_in_ha' is ignored when this option is True, since a backup is always deleted from Home Assistant after it gets uploaded to Google Drive.  Some find this useful if they only have enough space on their Home Assistant machine for one backup.

## FAQ

Read the [FAQ on GitHub](https://github.com/willkpalmer/hass_gdrive_backup/blob/master/FAQ.md#faq).

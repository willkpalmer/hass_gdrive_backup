# Logging

Everything GDrive Backup Utility logs can be identified as coming from this app and being about
backups. This page describes the format, for tools such as Log Doctor that find and report its
messages.

## Where messages go

| Where | What | How to read it |
| --- | --- | --- |
| The add-on's log | Everything at `console_log_level` (default `INFO`) and above | Settings > Add-ons > GDrive Backup Utility > Log, or the Supervisor API `GET /addons/<slug>/logs` |
| Home Assistant's log | Warnings and errors only | `home-assistant.log`, Settings > System > Logs, or the `system_log` integration |
| The add-on's web UI | Everything at `log_level` (default `DEBUG`) | The "Logs" page in the add-on |

Messages reach Home Assistant's log through the `system_log.write` service, so Home Assistant
writes them in its usual format and they show up alongside every other integration's. This can be
turned off with the `log_to_home_assistant` option. The same message from the same logger is only
sent to Home Assistant once every 15 minutes, so a problem that keeps repeating doesn't flood its
log; the add-on's own log still has every occurrence.

## Line format

Lines use Home Assistant's own log format:

```
2026-09-26 14:26:31.123 ERROR (MainThread) [hass_gdrive_backup.drive.drivesource] Google Drive returned HTTP 503
```

`<date> <time>.<milliseconds> <LEVEL> (<thread>) [<logger>] <message>`, in local time. Levels are
`DEBUG`, `INFO`, `WARNING`, `ERROR` and `CRITICAL` (plus `TRACE`, below `DEBUG`, which is only
shown when turned on). Exceptions are logged as a message followed by traceback lines, which don't
repeat the prefix. In the add-on's log, lines may be wrapped in terminal color codes
(`\x1b[...m`), which should be stripped before matching.

A regular expression that matches the first line of each message:

```
^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) (DEBUG|INFO|WARNING|ERROR|CRITICAL) \(([^)]*)\) \[(hass_gdrive_backup(?:\.[^\]]*)?)\] (.*)$
```

## Logger names

Every logger name starts with **`hass_gdrive_backup`**, the add-on's slug. That's how to tell this
app's messages apart from anything else, in either log: in Home Assistant's log they appear with
logger `hass_gdrive_backup.<area>`, and in the add-on's log every line does.

The rest of the name says which part of the app logged it:

| Logger | Area |
| --- | --- |
| `hass_gdrive_backup.ha.hasource` | Creating, listing, deleting and restoring backups in Home Assistant |
| `hass_gdrive_backup.ha.corebackups`, `.ha.hawebsocket` | Home Assistant's own backup schedule and settings |
| `hass_gdrive_backup.ha.haupdater` | Sensors, stale-backup notifications and the notify service |
| `hass_gdrive_backup.ha.mqtt` | MQTT discovery sensors |
| `hass_gdrive_backup.drive.*` | Uploading to, downloading from and managing Google Drive |
| `hass_gdrive_backup.creds.*` | Google Drive sign-in and token refresh |
| `hass_gdrive_backup.model.*` | Syncing: deciding what to back up, upload and clean up |
| `hass_gdrive_backup.util.*` | Networking and DNS, backoff, disk space |
| `hass_gdrive_backup.ui.*` | The add-on's web UI |
| `hass_gdrive_backup.server.*` | The auth server (only when running it yourself) |
| `hass_gdrive_backup.starter` | Startup. Logs `GDrive Backup Utility v<version> starting` |

These follow the code's module layout and can change between versions, but the
`hass_gdrive_backup` prefix won't.

## Finding backup problems

- Any `WARNING` or worse from a `hass_gdrive_backup.*` logger is a backup problem worth reporting.
- The problems users most need to know about also set `binary_sensor.backups_stale` to `on` and
  create a persistent notification titled "GDrive Backup Utility is Having Trouble", so a report can
  check those to tell a transient error from backups that have actually stopped.

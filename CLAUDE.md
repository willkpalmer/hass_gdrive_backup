# Working in this repository

## Every change bumps the version

Every commit that changes the add-on (code, config, dependencies, Dockerfile,
docs shipped with the add-on) must also:

1. Bump `version` in `hass_gdrive_backup/config.yaml` (semantic
   versioning: patch for fixes/small changes, minor for features).
2. Add a matching `## v<version> [YYYY-MM-DD]` entry at the top of
   `hass_gdrive_backup/CHANGELOG.md` (the file uses CRLF line endings).

On push to `master`, `.github/workflows/release.yml` creates a `v<version>`
GitHub Release if one doesn't exist yet. HACS and the add-on store only offer
an update when the version changes, so a change without a bump never reaches
users.

The version restarted at 0.1.0 for this fork. Don't change
`AUTH_SERVER_COMPATIBILITY_VERSION` in `hass_gdrive_backup/backup/config/settings.py`
to match: it's the version reported to the original add-on's shared token server,
which treats anything below 0.101.3 as a legacy client and breaks Google Drive sign-in.

## Every change is merged and released

Once a change is committed (with its version bump) and its checks pass, merge it
into `master` and push, so the Release workflow publishes `v<version>`. Then
confirm the release exists. Don't leave finished work sitting on a branch.

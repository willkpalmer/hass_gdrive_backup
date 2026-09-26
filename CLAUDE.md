# Working in this repository

## Every change bumps the version

Every commit that changes the add-on (code, config, dependencies, Dockerfile,
docs shipped with the add-on) must also:

1. Bump `version` in `hassio-google-drive-backup/config.yaml` (semantic
   versioning: patch for fixes/small changes, minor for features).
2. Add a matching `## v<version> [YYYY-MM-DD]` entry at the top of
   `hassio-google-drive-backup/CHANGELOG.md` (the file uses CRLF line endings).

On push to `master`, `.github/workflows/release.yml` creates a `v<version>`
GitHub Release if one doesn't exist yet. HACS and the add-on store only offer
an update when the version changes, so a change without a bump never reaches
users.

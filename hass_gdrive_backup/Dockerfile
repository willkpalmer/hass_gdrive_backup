# Home Assistant's Python base image. It's multi-arch, so Docker picks the right one for the device.
# The Supervisor can still override it with the BUILD_FROM build argument.
ARG BUILD_FROM=ghcr.io/home-assistant/base-python:3.13-alpine3.24
FROM $BUILD_FROM

LABEL org.opencontainers.image.title="GDrive Backup Utility" \
      org.opencontainers.image.description="Automatically back up Home Assistant to Google Drive, and restore from it" \
      org.opencontainers.image.source="https://github.com/willkpalmer/hass_gdrive_backup" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app
COPY requirements-addon.txt addon_deps.sh /app/
RUN sh ./addon_deps.sh
COPY . /app

EXPOSE 1627
EXPOSE 8099
ENTRYPOINT ["python3", "-m", "backup"]

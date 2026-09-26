#!/bin/sh
set -e

# fping is used by the addon's connectivity diagnostics.
apk add --no-cache fping

# Build dependencies are only needed if a wheel isn't available for this
# platform, so install them temporarily and remove them afterward.
apk add --no-cache --virtual .build-deps build-base linux-headers libffi-dev
pip3 install --no-cache-dir --upgrade pip wheel setuptools
pip3 install --no-cache-dir -r requirements-addon.txt
apk del .build-deps

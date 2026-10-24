#!/bin/sh
# Install a built apk into *this* Alpine and verify it runs.
#
#   TAG=v1.13.20 APK=/work/artifacts/py3-pymupdf-1.13.20-r20261022.apk \
#     sh scripts/run-tests.sh
#
# Used by CI (one job per Alpine release in the install scope) and by
# scripts/derive-matrix.sh when probing forward compatibility.
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
APK=${APK:?set APK to the .apk to test}
TAG=${TAG:-unknown}

log() { printf '>>> %s\n' "$*"; }

log "alpine $(cat /etc/alpine-release) | python $(python3 -V 2>&1 || echo missing)"
python3 -V >/dev/null 2>&1 || { apk add --no-cache python3 >/dev/null; }

log "installing $APK"
apk add --allow-untrusted "$APK" >/dev/null
python3 -c 'import fitz; print(">>> fitz %s -> mupdf %s" % (fitz.VersionBind, fitz.VersionFitz))'

log "smoke test"
python3 "$REPO/tests/smoke.py"

log "feature test"
python3 "$REPO/tests/feature.py"

log "PASS: $TAG on alpine $(cat /etc/alpine-release)"

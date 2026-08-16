#!/usr/bin/env bash
set -euo pipefail
appdir=${1:?usage: build_appimage.sh N0TE.AppDir [output]}
output=${2:-N0TE-Linux-Development-x86_64.AppImage}
test -x "$appdir/AppRun" || { echo "Invalid AppDir: AppRun is missing or not executable" >&2; exit 2; }
command -v appimagetool >/dev/null 2>&1 || { echo "appimagetool is an external build input; no archive will be mislabeled as AppImage" >&2; exit 3; }
ARCH=${ARCH:-$(uname -m)} appimagetool "$appdir" "$output"

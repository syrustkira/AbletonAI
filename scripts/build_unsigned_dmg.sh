#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STAGE=${1:-"$ROOT/build/macos/dmg-root"}
OUT=${2:-"$ROOT/build/macos/N0TE-Development-Unsigned.dmg"}
if ! command -v hdiutil >/dev/null 2>&1; then echo "hdiutil unavailable: deterministic DMG input remains at $STAGE" >&2; exit 69; fi
rm -f "$OUT"
hdiutil create -fs HFS+ -volname "N0TE Development" -srcfolder "$STAGE" -format UDZO "$OUT"
echo "Unsigned, unnotarized development DMG: $OUT"

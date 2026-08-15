#!/bin/bash
set -e
APP="$HOME/Library/Application Support/N0TE Ableton AI"
LAUNCHER="$APP/launchers/UNINSTALL_N0TE.command"
if [ ! -x "$LAUNCHER" ]; then
  echo "N0TE installed uninstaller was not found. Nothing will be guessed or deleted."
  exit 0
fi
exec "$LAUNCHER"

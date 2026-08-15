#!/bin/bash
set -e
APP="$HOME/Library/Application Support/N0TE Ableton AI"
LAUNCHER="$APP/launchers/START_N0TE.command"
if [ ! -x "$LAUNCHER" ]; then
  echo "N0TE is not installed yet. Run INSTALL_N0TE_MAC.command first."
  exit 1
fi
exec "$LAUNCHER"

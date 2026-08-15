#!/usr/bin/env bash
set -euo pipefail
out="${TMPDIR:-/tmp}/n0te-trace-coverage"
rm -rf "$out"
python3 -m trace --count --missing --summary --coverdir "$out" --module unittest discover -s tests
rm -rf "$out"

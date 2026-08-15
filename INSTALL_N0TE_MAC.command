#!/bin/bash
# N0TE Ableton AI macOS bootstrap installer.
# Recommended first-run path. Works even when Python is not installed yet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
N0TE_PY_INSTALLER="$SCRIPT_DIR/INSTALL_N0TE_ABLETON_AI.py"

# Pinned official Python.org maintenance release validated for N0TE.
PYTHON_VERSION="3.13.15"
PYTHON_SERIES="3.13"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-macos11.pkg"
PYTHON_SHA256="3b7eaf7f29825f796e8267024435540ddf1f17fc9a97ad58095daa7a75bfdcd3"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

say() { printf '%s\n' "$*"; }
fail() { say ""; say "ERROR: $*" >&2; exit 1; }

pause_on_error() {
  code="${1:-$?}"
  if [ "$code" -ne 0 ]; then
    say ""
    say "N0TE installation did not complete. The N0TE installer will not intentionally leave a half-installed N0TE update."
    if [ -t 0 ]; then
      read -r -p "Press Return to close…" _ || true
    fi
  fi
  exit "$code"
}
trap 'code=$?; pause_on_error "$code"' EXIT

if [ "${N0TE_BOOTSTRAP_ALLOW_NON_MAC:-0}" != "1" ]; then
  [ "$(uname -s)" = "Darwin" ] || fail "This bootstrap installer is for macOS."
fi

[ -f "$N0TE_PY_INSTALLER" ] || fail "Bundled N0TE Python installer is missing: $N0TE_PY_INSTALLER"

is_apple_toolchain_python() {
  case "$1" in
    /usr/bin/python3|/Applications/Xcode.app/*|/Library/Developer/CommandLineTools/*) return 0 ;;
    *) return 1 ;;
  esac
}

version_ok() {
  candidate="$1"
  is_apple_toolchain_python "$candidate" && return 1
  "$candidate" -c 'import sys; ok = sys.version_info >= (3,10) and sys.prefix == sys.base_prefix; raise SystemExit(0 if ok else 1)' >/dev/null 2>&1
}

find_python() {
  candidates=""
  # Prefer stable base interpreters over PATH shims/virtual environments.
  for p in \
    "/Library/Frameworks/Python.framework/Versions/${PYTHON_SERIES}/bin/python${PYTHON_SERIES}" \
    "/Library/Frameworks/Python.framework/Versions/${PYTHON_SERIES}/bin/python3" \
    "/usr/local/bin/python${PYTHON_SERIES}" \
    "/usr/local/bin/python3" \
    "/opt/homebrew/bin/python3"; do
    candidates="$candidates\n$p"
  done
  if command -v python3 >/dev/null 2>&1; then
    candidates="$candidates\n$(command -v python3)"
  fi
  printf '%b\n' "$candidates" | while IFS= read -r p; do
    [ -n "$p" ] || continue
    [ -x "$p" ] || continue
    if version_ok "$p"; then
      printf '%s\n' "$p"
      return 0
    fi
  done
}

ask_yes_no() {
  prompt="$1"
  if command -v osascript >/dev/null 2>&1 && [ "${N0TE_BOOTSTRAP_NO_GUI:-0}" != "1" ]; then
    result="$(osascript -e "display dialog \"$prompt\" buttons {\"Cancel\", \"Continue\"} default button \"Continue\" with title \"N0TE Ableton AI\"" -e 'button returned of result' 2>/dev/null || true)"
    [ "$result" = "Continue" ]
    return
  fi
  printf '%s [Y/n] ' "$prompt"
  read -r answer
  case "$answer" in
    n|N|no|NO|No) return 1 ;;
    *) return 0 ;;
  esac
}

verify_python_https() {
  "$1" - <<'PY' >/dev/null 2>&1
import urllib.request
with urllib.request.urlopen("https://www.python.org/", timeout=20) as response:
    if getattr(response, "status", 200) >= 400:
        raise SystemExit(1)
PY
}

install_python_certificates_if_needed() {
  python_bin="$1"
  if verify_python_https "$python_bin"; then
    return 0
  fi

  case "$python_bin" in
    /Library/Frameworks/Python.framework/Versions/${PYTHON_SERIES}/*|/usr/local/bin/python${PYTHON_SERIES}|/usr/local/bin/python3)
      cert_script="/Applications/Python ${PYTHON_SERIES}/Install Certificates.command"
      if [ -f "$cert_script" ]; then
        say "Installing Python HTTPS root certificates…"
        /bin/bash "$cert_script" || fail "Python installed, but its certificate setup failed."
      fi
      ;;
  esac

  verify_python_https "$python_bin" || fail "Python is installed, but HTTPS certificate verification is not working. N0TE needs HTTPS for the pinned bridge and OpenAI API."
}

PYTHON_BIN="$(find_python | head -n 1 || true)"
if [ "${N0TE_BOOTSTRAP_FORCE_MISSING_PYTHON:-0}" = "1" ]; then
  PYTHON_BIN=""
fi

if [ -n "$PYTHON_BIN" ]; then
  say "Compatible Python found: $($PYTHON_BIN --version 2>&1)"
  say "Using: $PYTHON_BIN"
  if [ "${N0TE_BOOTSTRAP_SKIP_HTTPS_CHECK:-0}" != "1" ]; then
    install_python_certificates_if_needed "$PYTHON_BIN"
  fi
else
  say "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ was not found."
  say ""
  say "N0TE can download and install Python ${PYTHON_VERSION} from Python.org."
  say "The package is pinned and its SHA-256 checksum and Python Software Foundation signature will be verified before installation."
  say "Installing Python requires your macOS administrator password."
  say ""

  if ! ask_yes_no "Python is required by the N0TE companion. Download and install Python ${PYTHON_VERSION} from Python.org now?"; then
    fail "Python installation was cancelled. N0TE was not installed."
  fi

  command -v curl >/dev/null 2>&1 || fail "macOS curl was not found."
  command -v shasum >/dev/null 2>&1 || fail "macOS shasum was not found."
  command -v pkgutil >/dev/null 2>&1 || fail "macOS pkgutil was not found."
  command -v sudo >/dev/null 2>&1 || fail "macOS sudo was not found."

  TMP_DIR="$(mktemp -d -t n0te-python.XXXXXX)"
  PKG="$TMP_DIR/python-${PYTHON_VERSION}-macos11.pkg"
  cleanup() { rm -rf "$TMP_DIR" 2>/dev/null || true; }
  trap 'code=$?; cleanup; pause_on_error "$code"' EXIT

  say "Downloading Python ${PYTHON_VERSION} from Python.org…"
  curl --location --fail --show-error --progress-bar "$PYTHON_URL" --output "$PKG"

  actual_sha="$(shasum -a 256 "$PKG" | awk '{print $1}')"
  [ "$actual_sha" = "$PYTHON_SHA256" ] || fail "Python package checksum verification failed. Refusing to install it."
  say "Python package checksum verified."

  say "Checking Apple package signature…"
  signature_output="$(pkgutil --check-signature "$PKG" 2>&1)" || fail "Python package signature check failed."
  printf '%s\n' "$signature_output" | grep -F "Python Software Foundation" >/dev/null 2>&1 || fail "Python package was signed, but not by the expected Python Software Foundation identity."
  printf '%s\n' "$signature_output" | grep -F "BMM5U3QVKW" >/dev/null 2>&1 || fail "Python package signer did not include the expected Python Software Foundation Apple Developer ID BMM5U3QVKW."
  say "Python Software Foundation package signature verified (BMM5U3QVKW)."

  if [ "${N0TE_BOOTSTRAP_DRY_RUN:-0}" = "1" ]; then
    say "Dry run: prerequisite download, checksum, and signer validation succeeded."
    cleanup
    trap - EXIT
    exit 0
  fi

  say ""
  say "macOS may now ask for your administrator password to install Python."
  sudo -v
  sudo /usr/sbin/installer -pkg "$PKG" -target /

  cleanup
  trap 'code=$?; pause_on_error "$code"' EXIT

  PYTHON_BIN="$(find_python | head -n 1 || true)"
  [ -n "$PYTHON_BIN" ] || fail "Python installed, but N0TE could not locate Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+."
  say "Python installed successfully: $($PYTHON_BIN --version 2>&1)"
  install_python_certificates_if_needed "$PYTHON_BIN"
fi

if [ "${N0TE_BOOTSTRAP_VALIDATE_ONLY:-0}" = "1" ]; then
  say "Bootstrap validation OK. Compatible Python: $PYTHON_BIN"
  trap - EXIT
  exit 0
fi

say ""
say "Starting N0TE Ableton AI installer…"
"$PYTHON_BIN" "$N0TE_PY_INSTALLER" install "$@"

trap - EXIT
say ""
say "N0TE bootstrap installation completed."
if [ -t 0 ]; then
  read -r -p "Press Return to close…" _ || true
fi

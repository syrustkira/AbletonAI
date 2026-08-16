# ADR 0004: macOS consumer bundle and mutable-state boundary

Status: Accepted

N0TE's consumer entrypoint is `N0TE.app/Contents/MacOS/N0TE`, which invokes only the private runtime at `Contents/Frameworks/Python/bin/python3`. It never falls back to Python, pip, Homebrew, git, or developer tooling from `PATH`. The deterministic builder fails without an approved runtime unless explicitly producing a non-consumer-ready unsigned development staging artifact.

The app bundle is read-only program state. Mutable product data belongs under `~/Library/Application Support/N0TE`, logs under `~/Library/Logs/N0TE`, and caches under `~/Library/Caches/N0TE`; recovery, updates, and rollback have dedicated subdirectories. Legacy state is copied non-destructively only when the new data directory does not exist.

One advisory file lock owns the local Core instance. A second launch opens the existing localhost UI when reachable and never kills another process. Native/host component replacement is delegated to an external helper that waits for voluntary exit, verifies the complete staged app, backs up, replaces, verifies/relaunches, and rolls back application files only.

The current entitlements file is empty because the portable Core needs no Apple entitlement. Production signing keys, hardened-runtime signing, notarization, stapling, approved private CPython payload, real macOS metadata/process evidence, and real Ableton acceptance remain external acceptance requirements.

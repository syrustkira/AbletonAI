# N0TE Ableton AI 1.2.4 Installer Audit

## Intended first-run behavior

`INSTALL_N0TE_MAC.command` is the only recommended public first-run entrypoint. It must work on a Mac with no user-installed Python.

### Prerequisite flow

- Reuse a stable base Python 3.10+ when available.
- Do not rely on Apple/Xcode `/usr/bin/python3` or an active virtual environment.
- If missing, explicitly ask before downloading Python.
- Download Python 3.13.15 from Python.org.
- Verify published SHA-256: `3b7eaf7f29825f796e8267024435540ddf1f17fc9a97ad58095daa7a75bfdcd3`.
- Require package-signature output identifying the Python Software Foundation and Apple Developer ID `BMM5U3QVKW`.
- Install through macOS `/usr/sbin/installer` with administrator authorization.
- Complete Python.org `Install Certificates.command` when HTTPS is not yet functional.
- Verify Python HTTPS before starting N0TE installation.

## N0TE install flow

- Resolve explicit User Library, environment override, previously saved User Library, standard locations, then macOS folder chooser.
- Preserve `~/.n0te-ableton-ai`.
- Download exact pinned `bschoepke/ableton-live-mcp` commit.
- Reject unsafe ZIP paths.
- Require expected commit directory and required files.
- Verify `Ableton_Live_MCP/bridge.py` against pinned Git blob SHA-1 `ecc4fd7945ea748582b0534bf5ea119a878933eb`.
- Back up legacy prototypes and anything occupying managed install paths.
- Distinguish rollback-only version snapshots from pre-N0TE backups that should be restored on uninstall.
- Copy the Remote Script and preserve its MIT license.
- Copy the N0TE app and GPL-3.0/modification notices.
- Optionally build AgentAudioTap; restore a prior tap if optional build fails.
- Generate start/health/uninstall launchers pinned to the exact chosen Python executable.
- Write install manifest atomically.
- Persist the selected User Library so installed health checks and future updates inspect the same library.
- Delete obsolete rollback-only version snapshots after a later update succeeds, while retaining pre-N0TE restore backups.

## Failure semantics

### Failed fresh install

Remove files created by the failed transaction and restore paths displaced by the transaction.

### Failed update

Restore the immediately previous working N0TE app/Remote Script.

### Successful uninstall

Remove current N0TE-managed install paths and restore the known **pre-N0TE** occupants, not the previous N0TE version. Keep user state/history. Archive the manifest as `last_uninstalled_manifest.json`.

## Security boundaries

- N0TE bootstrap requires HTTPS, published checksum and expected PSF signer for Python prerequisite.
- Upstream bridge is commit-pinned and core bridge content is independently blob-checked.
- ZIP path traversal is rejected.
- Uninstaller refuses touched/restore destinations outside the known managed-path allowlist.
- Backup sources used during uninstall must live inside the N0TE backup directory.
- Persistent state is user-scoped, not installed system-wide.

## Acceptance limits

The automated environment can validate shell/Python logic, sandbox lifecycle semantics, UI/server smoke behavior and source integrity rules. It cannot reproduce the real macOS authorization UI, Gatekeeper behavior, Python `.pkg` installation, Ableton's Control Surface loading, Max for Live build behavior, or the exact user's custom filesystem permissions. Those remain target-Mac acceptance tests.

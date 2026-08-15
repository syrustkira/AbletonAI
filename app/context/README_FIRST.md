# N0TE Ableton AI 1.2.4 — Creative Coproducer Hardening + Audited macOS Bootstrap

N0TE is a local TellMeN0TE-specific Ableton Live production coproducer. Its primary interaction is:

> **TYPE → ANALYZE → CONSULT → PROPOSE → IMPLEMENT AFTER APPROVAL → REVIEW → KEEP / ADJUST / UNDO**

The project is intentionally broader than any one feature such as plugin simplification. Read `PROJECT_BLUEPRINT.md` for the stable architecture, `docs/ROADMAP.md` for build order, `AGENTS.md` for Codex/agent rules, and `INSTALLER_AUDIT.md` for the installer-specific correctness review.

## Recommended installation path

**You do not need Python installed beforehand.**

1. Quit Ableton Live.
2. Unzip this package.
3. Double-click `INSTALL_N0TE_MAC.command`.
4. If a compatible non-Apple-toolchain Python 3.10+ is already installed, N0TE reuses it.
5. Otherwise N0TE asks permission to download the pinned official Python.org Python 3.13.15 macOS installer.
6. The bootstrap verifies the published SHA-256 checksum and checks that the package signature identifies the Python Software Foundation before invoking the macOS installer.
7. After Python installation, the bootstrap completes Python's HTTPS certificate setup and verifies HTTPS before continuing.
8. The transactional N0TE installer then locates your Ableton User Library, downloads and verifies the pinned Ableton bridge, backs up only paths it needs to replace, installs N0TE, and creates launchers.
9. Restart Ableton Live and, if needed, select `Ableton_Live_MCP` as a Control Surface.
10. Start `~/Desktop/START N0TE Ableton AI.command`, then save your OpenAI API key in Settings.

If your Ableton User Library is not in a standard location and has not been installed previously, the macOS installer can prompt you to select it. Future updates remember that path from the install manifest.

### macOS Gatekeeper note

This personal alpha bundle is not Apple Developer-ID signed/notarized as a N0TE application. Depending on macOS quarantine/Gatekeeper settings, you may need to **right-click `INSTALL_N0TE_MAC.command` → Open** the first time. The Python prerequisite package itself is separately verified as an official Python Software Foundation-signed package before installation.

## Installer guarantees in 1.2.4

- One recommended public installer: `INSTALL_N0TE_MAC.command`.
- Python backend uses only the Python standard library.
- Python.org prerequisite install occurs only after explicit approval when no suitable Python is present.
- Apple/Xcode toolchain `/usr/bin/python3` is deliberately not treated as N0TE's runtime.
- Virtual-environment interpreters are not selected as the persistent N0TE runtime.
- Exact interpreter path is pinned into installed launchers and the manifest.
- Python HTTPS certificates are verified before N0TE proceeds.
- Pinned upstream bridge commit: `70f7df9192b78d9bd9405f369c9e046c88f1610e`.
- The core upstream `bridge.py` is also checked against the expected Git blob SHA-1 before installation.
- Archive path traversal is rejected before extraction.
- Existing N0TE upgrades are rollback-safe: failure restores the immediately previous working app/Remote Script.
- Uninstall semantics are separate from rollback semantics: uninstall restores **pre-N0TE** files where known instead of restoring the previous N0TE version.
- Custom Ableton User Library location is persisted across updates.
- Installed HEALTHCHECK reads the persisted User Library location instead of assuming Ableton defaults.
- Rollback-only snapshots from superseded successful updates are cleaned so the backup directory does not grow with stale N0TE versions.
- The local UI remains loadable when Ableton is offline and reports the bridge-offline state without losing app/config/context status.
- Install manifest is written atomically.
- Persistent N0TE state/history under `~/.n0te-ableton-ai` is preserved across updates and normal uninstall.
- The installed application contains its own uninstaller launcher, so the downloaded ZIP does not have to be kept forever.
- Manifest-driven uninstall is allowlisted to known N0TE/Ableton paths and will refuse unexpected destinations.
- Legacy prototype locations are quarantined/backed up rather than blindly deleted.
- AgentAudioTap build remains optional; if its build fails, an existing prior AudioTap is restored and the core N0TE install continues.
- GPL-3.0 project license and the MIT license for the pinned Ableton bridge are included/preserved.

## What the coproducer currently includes

### Full context/build architecture

- Canonical `N0TE_CONTEXT_PACK.json` containing artist goals, creative DNA, technical background, finishing guardrails, native-first rules, product architecture and roadmap.
- `PROJECT_BLUEPRINT.md` packaged with the app so future builds do not collapse around the latest single feature discussed.
- Recent transaction context is sent into follow-up conversations, so comments like “better but thinner” can refer to the exact recent edit.
- Per-song local conversation persists across companion-server restarts.
- Unsaved Sets use a stable N0TE identity and migrate semantic state into the saved-path identity when the Set is saved.
- Shipped context is versioned separately from user overrides.

### Exact selection awareness

N0TE reads, where Live exposes it:

- selected normal, return, or master track
- selected device
- exposed device parameters and reported latency metadata
- detail clip
- selected MIDI note data

### DISCOVER

Search order:

1. current Set audio/clips
2. Ableton Browser
3. N0TE cached Live library index
4. Openverse audio
5. Freesound when configured
6. general web click-through only when dedicated providers fail

N0TE records per-song discovery outcomes as **tried / used / rejected / saved**, retaining source/license metadata where provided.

### CREATE

The selected MIDI clip can be inspected and existing note IDs can be changed through the same approval-gated transaction system. Original note values are captured so `Undo N0TE` can restore changed pitch, timing, duration, velocity, mute, probability, velocity deviation and release velocity values.

### Native-first capability resolver

Solution order:

> **already in set → Ableton native → already owned plugin/rack → N0TE extension only for a missing capability → web/external/new only if genuinely needed**

### Safety/recovery retained

- proposal gating
- action validation
- set-signature stale-proposal rejection
- inverse transaction journal
- N0TE Undo that stops on partial rollback error rather than firing blind native Undo
- checkpoints and deterministic state comparison
- per-song decision ledger
- asset/path health checks
- versioned context and user overrides

## Important simplification rule

N0TE does **not** optimize toward “stock everything.” It asks what job must survive, whether advanced features are actually in use, whether a simpler route already exists, whether the replacement genuinely reduces total complexity, and whether the result survives A/B listening. CPU savings remain unknown unless measured.

## Current Song-Ready status

Real-Mac acceptance has now confirmed that the Remote Script and N0TE UI can communicate with Live when Ableton is pointed at the correct User Library. The first run also exposed two items that must be hardened before trusting N0TE mutations on a real song: explicit song/Set transaction ownership for `Undo N0TE`, and deterministic User Library/Remote Script diagnostics.

**Until Gate 1 in `docs/ROADMAP.md` is completed and passes the disposable-Set acceptance checklist, use v1.2.4 mutations only in disposable test Sets. Read-only analysis is appropriate for continued testing.**

The bounded implementation handoff for Codex is `CODEX_SONG_READY_HANDOFF.md`.

## Recommended first acceptance test

Use a disposable Ableton Set first:

1. Confirm the installer reports success and creates the Desktop start/health launchers.
2. Restart Live and confirm `Ableton_Live_MCP` loads.
3. Start N0TE and run HEALTH.
4. Select normal/return/master tracks and native/third-party devices; confirm selection awareness.
5. Ask harmless read-only questions before applying edits.
6. Apply and undo a rename/mute/pan change.
7. Test stale-proposal rejection after manually changing Live.
8. Test a reversible MIDI edit.
9. Test DISCOVER local-first then online fallback.
10. Restart N0TE and confirm song context/conversation persist.
11. Run FINISH and confirm it does **not** claim true bounce readiness without audio preflight.

## Environment

Companion app:

`~/Library/Application Support/N0TE Ableton AI`

Persistent state:

`~/.n0te-ableton-ai`

Installed Remote Script:

`<Ableton User Library>/Remote Scripts/Ableton_Live_MCP`

Installed uninstaller:

`~/Library/Application Support/N0TE Ableton AI/launchers/UNINSTALL_N0TE.command`

## Known product limits

These are not installer defects; they are still-unimplemented roadmap capabilities:

- no actual AudioTap analysis/listening pipeline yet
- no Plugin Delta / Reference Delta / Finish Dry Run audio evidence yet
- simplification replacement devices start at defaults; arbitrary plugin-to-native parameter translation is not implemented
- DISCOVER does not yet perform licensed automatic web import / `Try in Song`
- Music Map dependency intelligence / Chord Followers are not yet complete
- safe duplicate/take-lane generative MIDI is not yet complete
- Production Recipes are not yet implemented
- plugin sandbox/characterization is not yet implemented
- Voice Lab/guide singing is not yet implemented
- deterministic Ableton capability catalog is curated rather than exhaustive
- OpenAI API usage is separate from a ChatGPT subscription

For exact shipped-vs-planned status, see `FEATURE_MATRIX.json` and `BUILD_VALIDATION.md`.

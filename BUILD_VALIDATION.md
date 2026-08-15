# N0TE Ableton AI 1.2.4 validation

## Automated checks

- Python source compilation: **PASS**
- macOS bootstrap/start/uninstall shell syntax (`bash -n`): **PASS**
- UI JavaScript syntax: **PASS**
- JSON parsing: **PASS**
- UI endpoint/backend consistency: **PASS**
- unit/regression/lifecycle tests: **59 PASS** in the Gate 1 implementation sweep
- local companion-server smoke test without Ableton: **PASS**; UI returns HTTP 200 and `/api/status` retains app/config/context metadata while reporting the Ableton bridge offline

- Python test coverage in final audit: **~52% overall**, with `n0te_server.py` at **~33%**; real-Live acceptance remains mandatory

## Installer-specific regressions covered

- existing compatible Python path
- no-Python dry-run prerequisite path
- correct Python checksum expectation
- wrong package signer rejection
- correct PSF signer acceptance
- bootstrap failure exit status remains nonzero after cleanup
- explicit User Library
- remembered nonstandard User Library
- install manifest schema/interpreter recording
- transaction rollback restores displaced paths
- simulated fatal upgrade failure restores previous app and Remote Script
- fresh install → update → uninstall restores pre-N0TE files instead of previous N0TE
- installed uninstaller presence
- manifest archival after uninstall
- legacy Python-dependent shell installer is not the recommended/public entrypoint
- custom User Library is used by the installed health check, not only by install/update
- previous rollback-only version snapshots are cleaned after a newer update completes successfully
- offline companion status remains usable instead of collapsing to a generic server error

## Hardening carried from 1.2.1+

- stable unsaved Set identity and save migration
- versioned base context + user override layer
- persistent per-song conversation
- recursive Rack device inventory
- discovery-intent normalization
- FINISH cannot claim true bounce readiness without audio preflight
- partial N0TE rollback stops without blind native Ableton Undo
- return/master selected-device context

## What automated validation does not prove

- macOS Gatekeeper behavior on the downloaded N0TE `.command`
- administrator authorization UI
- actual Python.org `.pkg` installation on the user's Mac
- actual `Install Certificates.command` execution on the target Mac
- Ableton Live loading the Remote Script in the user's exact Live version/edition
- Max for Live AgentAudioTap build/install on the user's machine
- real third-party plugin parameter exposure
- OpenAI/Freesound/Openverse availability and user credentials
- real audio analysis, because that N0TE layer is not implemented yet

## Deliberately not claimed in 1.2.4

- actual audio listening/AudioTap analysis pipeline
- Plugin Delta / Reference Delta / Finish Dry Run
- automatic arbitrary plugin-to-native parameter translation
- automatic licensed web sound import / Try in Song
- complete Music Map dependency/Chord Follower engine
- safe duplicate/take-lane generative MIDI transaction
- Production Recipes
- plugin sandbox
- Voice Lab / guide singer

## Real-Mac acceptance evidence — 2026-08-14

The first target-Mac/Live acceptance pass produced useful real-world evidence:

- Ableton initially did **not** show `Ableton_Live_MCP` because the configured Ableton User Library was wrong.
- After correcting the User Library setting, the Remote Script appeared in Live.
- After changing a Live setting and refreshing the Set in the N0TE UI, N0TE detected the updated Live state.

This proves the installed bridge/UI can communicate with the user's real Live environment when the correct User Library is configured. It also exposed a diagnostics gap: installation success alone does not prove that Live is using the same User Library path. `docs/ROADMAP.md` therefore makes a Remote Script/User Library Doctor part of the SONG-READY gate.

## Gate 1 implementation status

Gate 1 now binds new transactions and simplification experiments to the stable ProjectStore song key, scopes recent context and Undo, rejects legacy/cross-Set ownership guesses, revalidates Apply and recovery targets, and serializes mutations. Atomic state writes, proposal expiry, request limits/status classes, consistent local request policy, and Remote Script diagnostics are automated-test covered.

This is **implementation complete / real-Live acceptance pending**, not a SONG-READY claim. The canonical next acceptance target is the disposable-Set checklist in `CODEX_SONG_READY_HANDOFF.md`.

Reproducible dependency-free statement-coverage command: `bash scripts/coverage.sh`.

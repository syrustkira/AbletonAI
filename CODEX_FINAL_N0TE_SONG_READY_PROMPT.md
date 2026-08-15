# FINAL CODEX ONLINE PROMPT — N0TE SONG-READY

Repository: `syrustkira/AbletonAI`

Work from the current `main` branch, but make implementation changes on a new Codex task branch and prepare a PR back to `main`.

## Mission

Make the current N0TE v1.2.4 baseline **SONG-READY** so I can safely start a real new Ableton song with N0TE.

This is Gate 1 only. Do not implement later roadmap gates yet.

## Read before editing

Read these repository files in this order:

1. `AGENTS.md`
2. `PROJECT_BLUEPRINT.md`
3. `docs/ROADMAP.md`
4. `FEATURE_MATRIX.json`
5. `N0TE_CONTEXT_PACK.json`
6. `BUILD_VALIDATION.md`
7. `HARDENING_AUDIT.md`
8. `INSTALLER_AUDIT.md`
9. `CODEX_SONG_READY_HANDOFF.md`
10. `CODEX_N0TE_FULL_BUILD_AFTER_SONG_READY.md`

Treat `CODEX_SONG_READY_HANDOFF.md` as the authoritative detailed implementation specification for this task.

`CODEX_N0TE_FULL_BUILD_AFTER_SONG_READY.md` preserves the later backlog. Read it for architectural awareness, but **do not implement Gates 2–9 in this task**.

## Preflight

Before changing code:

- run `git status -sb`
- identify the base commit
- verify the real application, installer and test source is present
- verify there is no leftover `.n0te-import` transfer payload or `IMPORT_N0TE_PAYLOAD.py`
- if `.github/workflows/import-n0te.yml` remains from migration, remove/replace that one-shot migration workflow as part of the proper CI work
- run the current full baseline validation
- inspect the implementation and existing tests for all Gate 1 workstreams
- report any disagreement between code/tests, `PROJECT_BLUEPRINT.md`, `FEATURE_MATRIX.json`, `docs/ROADMAP.md`, and the handoff before changing behavior

Do not silently reinterpret conflicting requirements.

## P0 first: transaction ownership and Undo safety

The highest-priority known defect is that transactions/recent-change lookup can behave globally rather than being safely owned by the originating song/Live Set.

Implement the requirements in `CODEX_SONG_READY_HANDOFF.md`, including:

- bind every new mutation transaction to the current `ProjectStore.song_key(snapshot)` and stable Set/session identity
- retain Set path when available
- record before/after signatures and sufficient affected-target/post-state evidence for safe recovery
- scope operational recent/latest transaction lookup to the current song
- never inject another song's recent transaction into the current coproducer context
- refuse cross-Set `Undo N0TE`
- revalidate affected targets before inverse execution
- allow safe targeted Undo after unrelated user edits when the affected target is still compatible
- refuse/stop recovery when the affected target was changed incompatibly
- preserve partial-rollback fail-closed behavior
- never trigger blind native Ableton Undo as an automatic fallback
- preserve unsaved Set → Save As continuity
- preserve legacy unscoped transaction history but never guess ownership
- apply the same ownership/recovery rules to simplification experiments

Add regression tests that fail against the old behavior.

## Complete the rest of Gate 1

After P0 transaction safety, implement all remaining Gate 1 workstreams from the handoff:

### Apply / object targeting
- fresh Apply-time action revalidation
- stale proposal protection
- canonical recursive Live-object indexing for selection, validation and execution
- prefer stable exposed object IDs over raw indexes where practical
- do not broaden the approved mutation whitelist

### Persistent-state safety
- reusable atomic JSON writes for important product state
- stable store-owned locks
- serialize mutating Apply/Undo/experiment operations
- concurrency/state-corruption regression coverage
- backward-compatible state migrations

### Remote Script Doctor / HEALTH
Turn the real User Library failure mode into deterministic diagnostics:
- manifest User Library
- expected Remote Script location/structure
- required files
- Ableton bridge `127.0.0.1:8765`
- N0TE companion `127.0.0.1:8766`
- OpenAI credential configured/not-configured without exposing it
- latest Ableton `Log.txt` when discoverable
- relevant Remote Script/import/traceback/module/syntax errors
- distinguish “installed files” from “Live actually loaded script”
- identify likely User-Library mismatch without presenting heuristics as proof
- provide actionable repair guidance

### Server/API hardening
- meaningful HTTP error status classes
- request-body size limit
- consistent localhost Host/Origin protections
- proposal expiration/cleanup
- redacted rotating diagnostics
- never log API keys or sensitive full model/audio payloads
- only decompose `n0te_server.py` where characterization tests justify a bounded extraction

### CI / validation truth
- create permanent CI for the canonical automated checks
- define one reproducible coverage command
- improve meaningful server/failure/health/uninstall coverage where practical
- update documentation/status only for behavior actually implemented/proven

## Permanent invariants

Do not violate these to complete the task:

`TYPE → ANALYZE → CONSULT → PROPOSE → USER APPROVES → IMPLEMENT → REVIEW → KEEP / ADJUST / UNDO`

Every mutation path must preserve:

`PROPOSE → VALIDATE → USER APPROVAL → REVALIDATE → EXECUTE → JOURNAL → REVIEW → UNDO`

Knowledge Plane may be broad.
Action Plane must remain narrow, validated and reversible.

Default solution order:

`CURRENT SET → ABLETON NATIVE → ALREADY OWNED TOOL/RACK → N0TE EXTENSION → EXTERNAL/WEB/NEW`

Never:
- expose arbitrary `live_eval`, `live_exec`, Python or equivalent unrestricted mutation to normal AI
- weaken validation to make a test or feature pass
- claim audio was heard without actual captured audio
- claim CPU savings without measurement
- claim plugin equivalence from category alone
- destructively overwrite originals for experiments
- silently discard persistent user/song/context history
- build Gates 2–9 during this task

## Required validation

Run at minimum:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q app INSTALL_N0TE_ABLETON_AI.py
bash -n INSTALL_N0TE_MAC.command
bash -n START_N0TE_ABLETON_AI.command
bash -n UNINSTALL_N0TE_ABLETON_AI.command
python3 -m json.tool VERSION.json >/dev/null
python3 -m json.tool FEATURE_MATRIX.json >/dev/null
python3 -m json.tool N0TE_CONTEXT_PACK.json >/dev/null
```

Also run the repository's JavaScript syntax validation and new permanent CI/coverage checks where available.

## Definition of completion for Codex

Complete everything that can be implemented and deterministically tested in the repository/cloud environment.

Then:

1. commit the coherent Gate 1 implementation on your task branch
2. prepare a PR targeting `main`
3. give me:
   - preflight findings
   - root causes fixed
   - files changed
   - state/schema migrations
   - tests added
   - complete test/CI/coverage results
   - security/safety implications
   - documentation/status changes
   - anything that still requires real macOS/Ableton verification
4. return the exact **REAL-LIVE ACCEPTANCE CHECKLIST** from `CODEX_SONG_READY_HANDOFF.md`, updated only where the implementation genuinely requires it
5. stop

Do **not** mark N0TE fully SONG-READY merely because mocks/tests pass. Real Ableton acceptance is mine to perform after your PR.

Do not start the post–Song-Ready backlog yet.

The later preserved roadmap remains in:
`CODEX_N0TE_FULL_BUILD_AFTER_SONG_READY.md`

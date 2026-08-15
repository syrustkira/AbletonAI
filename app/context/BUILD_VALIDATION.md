# N0TE Ableton AI 1.2.4 validation

## Automated checks

- Python source compilation: **PASS**
- macOS bootstrap/start/uninstall shell syntax (`bash -n`): **PASS**
- UI JavaScript syntax: **PASS**
- JSON parsing: **PASS**
- UI endpoint/backend consistency: **PASS**
- unit/regression/lifecycle tests: **155 PASS**, including observability, Musical Panic, Artist World, Creator, recipes and Quick Edit regressions
- local companion-server smoke test without Ableton: **PASS**; UI returns HTTP 200 and `/api/status` retains app/config/context metadata while reporting the Ableton bridge offline

- Reproducible coverage: **PASS**; real-Live acceptance remains mandatory

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
- Remote Script Doctor accepts the pinned upstream root layout (`Ableton_Live_MCP/__init__.py` + `bridge.py`) and rejects an accidental duplicate nested `Ableton_Live_MCP` folder

## AI provider switchboard regressions covered

- Gemini provider selection routes N0TE structured inference through Gemini's native `generateContent` endpoint with the existing JSON Schema contract
- native Gemini structured calls use `x-goog-api-key` and do not forward the OpenAI bearer credential
- Gemini thought-text parts are excluded from the structured answer instead of being concatenated into JSON
- non-`STOP` candidates such as `MAX_TOKENS` are classified as incomplete and reported with bounded finish/token diagnostics
- the first malformed/incomplete Gemini candidate is discarded and one fresh schema-constrained retry is allowed; the malformed candidate is never punctuation-repaired
- Gemini 3 structured calls use low thinking initially and minimal thinking on the fresh retry; retry output budget may grow up to 2x, capped at 8192 tokens
- two invalid Gemini candidates still fail closed and never become an Ableton proposal
- Ollama resolves through the local OpenAI-compatible endpoint
- remote custom endpoints cannot use plaintext HTTP; localhost may
- existing Responses-style structured requests are translated to Chat Completions for non-Gemini compatible providers while retaining the JSON Schema contract
- Chat Completions structured output is converted back into N0TE's existing response shape
- provider selection is explicit; no automatic paid-provider fallback is enabled

## Hardening carried from 1.2.1+

- stable unsaved Set identity and save migration
- versioned base context + user override layer
- persistent per-song conversation
- recursive Rack device inventory
- discovery-intent normalization
- FINISH cannot claim true bounce readiness without audio preflight
- partial N0TE rollback stops without blind native Ableton Undo
- return/master selected-device context
- canonical governance/runtime context mirrors are regression-checked so packaged status cannot silently diverge from root product truth

## What automated validation does not prove

- macOS Gatekeeper behavior on the downloaded N0TE `.command`
- administrator authorization UI
- actual Python.org `.pkg` installation on the user's Mac
- actual `Install Certificates.command` execution on the target Mac
- Ableton Live loading the Remote Script in the user's exact Live version/edition
- Max for Live AgentAudioTap build/install on the user's machine
- real third-party plugin parameter exposure
- availability/quota of any selected cloud AI provider or user credential
- quality/performance of a selected local Ollama model on the user's Mac
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

Gate 1 now binds new transactions and simplification experiments to the stable ProjectStore song key, scopes recent context and Undo, rejects legacy/cross-Set ownership guesses, revalidates Apply and recovery targets, and serializes mutations. Review regressions additionally prove Set-anchor-only Save As migration, same-process unrelated-Set isolation, stable-ID Undo after track index shifts, deterministic same-second transaction chronology, and fail-closed ambiguous simplification recovery without native Undo. Atomic state writes, proposal expiry, malformed/oversized request handling, 404/409/503 failure classes, consistent local Host/Origin rejection, and Remote Script diagnostics are automated-test covered.

The closure sweep proves execute-success is journaled before fallible post-observation, same-path/different-Set targetless Undo refusal, actual coerced post-state recovery, serialization of explicit native Undo, locked proposal registries and song-state read/modify/write, parent-directory fsync, and offline-safe/credential-complete/latest-outcome Doctor behavior. Set ownership requires the scoped N0TE song key plus a matching recorded/current Live Set-session identity; saved path, process token, signature, or raw index alone is insufficient.

The real-Live acceptance pass additionally caught and corrected a Doctor-only false negative: the pinned Remote Script is installed directly as `Remote Scripts/Ableton_Live_MCP/{__init__.py,bridge.py}`. The Doctor now validates that actual installer/upstream layout rather than requiring an extra nested package directory.

The provider switchboard is transport-only. Gemini uses native structured output and now handles real-world malformed/incomplete candidates by isolating thought parts, checking finish metadata, discarding the bad candidate, and making at most one fresh schema-constrained retry. It never guess-repairs safety-critical JSON. This does not widen the Ableton action whitelist or bypass proposal validation, approval, mutation serialization, journaling, Set ownership, or N0TE Undo safety. Cloud-provider availability and local-model quality remain real-machine acceptance concerns.

This is **implementation complete / real-Live acceptance pending**, not a SONG-READY claim. The canonical next acceptance target is the disposable-Set checklist in `CODEX_SONG_READY_HANDOFF.md`.

Reproducible dependency-free statement-coverage command: `bash scripts/coverage.sh`.
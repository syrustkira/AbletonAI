# N0TE Ableton AI 1.2.4 validation

## Automated checks

- Python source compilation: **PASS**
- macOS bootstrap/start/uninstall shell syntax (`bash -n`): **PASS**
- UI JavaScript syntax: **PASS**
- JSON parsing: **PASS**
- UI endpoint/backend consistency: **PASS**
- unit/regression/lifecycle tests: **290 PASS**, including Gate 1 ownership/recovery invariants, fail-closed AI/network/update defaults, partial/corrupt runtime-config recovery, Vault outward-privacy enforcement, scoped creative-intent conflicts, objective-bound audition scoring, Song-product recovery, plugin-first portability assessment, ranged-analysis persistence, truncated-WAV refusal, evidence-gated DAW adapter health, distribution path confinement and displaced-file restoration, packaged provider bootstrap/local-Ollama routing, limiter-tail preservation, Creator revision/concurrency safety, stream backend fail-closed behavior, portable observability, rollback-compatible update enforcement, macOS post-launch health rollback, and persisted Settings hydration
- local companion-server smoke test without Ableton: **PASS**; UI returns HTTP 200 and `/api/status` retains app/config/context metadata while reporting the Ableton bridge offline
- Reproducible coverage: **PASS**; the coverage run independently executes the same **290 tests**

The canonical GitHub Actions run for this candidate also passes Python compilation, shell syntax, JSON parsing, and UI JavaScript validation. Real-Live acceptance remains mandatory before any SONG-READY promotion.

## Installer and distribution regressions covered

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
- generic distribution uninstall restores files displaced by N0TE instead of deleting them
- source, staged-payload, install-destination, backup, and private-runtime paths are confined beneath their declared roots; traversal/absolute paths fail closed
- installed uninstaller presence
- manifest archival after uninstall
- legacy Python-dependent shell installer is not the recommended/public entrypoint
- custom User Library is used by the installed health check, not only by install/update
- previous rollback-only version snapshots are cleaned after a newer update completes successfully
- offline companion status remains usable instead of collapsing to a generic server error
- Remote Script Doctor accepts the pinned upstream root layout (`Ableton_Live_MCP/__init__.py` + `bridge.py`) and rejects an accidental duplicate nested `Ableton_Live_MCP` folder

## AI provider and offline-runtime regressions covered

- Gemini provider selection routes N0TE structured inference through Gemini's native `generateContent` endpoint with the existing JSON Schema contract
- native Gemini structured calls use `x-goog-api-key` and do not forward the OpenAI bearer credential
- Gemini thought-text parts are excluded from the structured answer instead of being concatenated into JSON
- non-`STOP` candidates such as `MAX_TOKENS` are classified as incomplete and reported with bounded finish/token diagnostics
- the first malformed/incomplete Gemini candidate is discarded and one fresh schema-constrained retry is allowed; the malformed candidate is never punctuation-repaired
- Gemini 3 structured calls use low thinking initially and minimal thinking on the fresh retry; retry output budget may grow up to 2x, capped at 8192 tokens
- two invalid Gemini candidates still fail closed and never become an Ableton proposal
- Ollama resolves through the local OpenAI-compatible endpoint
- OFFLINE NetworkPolicy evaluates the actual routed provider destination, so local Ollama remains available while cloud Gemini/OpenAI remain blocked
- remote custom endpoints cannot use plaintext HTTP; localhost may
- existing Responses-style structured requests are translated to Chat Completions for non-Gemini compatible providers while retaining the JSON Schema contract
- Chat Completions structured output is converted back into N0TE's existing response shape
- provider selection is explicit; no automatic paid-provider fallback is enabled
- the packaged application explicitly rebinds provider state to product paths and seeds a first-ever launch with AI `off` / network `offline` before provider routing starts
- a fresh unconfigured runtime seeds AI `off`, network `offline`, community disabled, and automatic network update/install behavior disabled
- valid existing user choices are preserved; only missing safety defaults are filled
- corrupt runtime config bytes are preserved under `Recovery/` before safe defaults replace the unreadable active config
- explicit First Run OFF/OFFLINE choices synchronize into the runtime config
- `NetworkPolicy()` and an absent/unknown network-mode value fail closed to OFFLINE while retaining loopback access for local N0TE components
- provider-transport characterization must explicitly opt into an online provider rather than relying on an unsafe implicit default

## Audio, Song-product, and capability correctness covered

- streaming WAV analysis refuses a declared/truncated data chunk instead of spinning indefinitely
- ranged `AnalysisKey` values survive JSON tuple/list round-trips and can be retrieved from persisted analysis history
- offline limiter lookahead preserves the complete song tail and reports its lookahead latency while rendering in latency-compensated form
- Song sessions require explicit/evidence-supported exit-condition status before being called complete
- Vault evidence cannot implicitly become AI, sync, publication, or community-visible content
- Creative Twin conflicts are scoped to relevant technical/creative evidence rather than globally suppressing unrelated work
- Audition Lab does not invent a generic measurement winner; measurement ranking requires an explicit job-specific objective
- corrupt Song-product state is preserved for recovery and mutation fails closed until recovery
- third-party plugin identity is assessed before a Device is labelled host-native during portability analysis
- capability health remains granular through READY/DEGRADED/UNAVAILABLE/RECOVERING states
- DAW discovery will not promote adapter health/capability counts from an unverified claim; detected/claimed adapters remain unavailable until evidence is attached
- authority output is labelled as a policy summary rather than live mutation authority
- delivery receipts explicitly mark unavailable pre-render analysis instead of silently storing an ambiguous null

## Creator, stream, observability, and update safety covered

- recipe/edit changes increment the durable ContentProject revision and invalidate stale publication approval
- CreatorService serializes project read-modify-write workflows so concurrent edits do not silently lose one another
- stream TEST/LIVE state depends on a successful backend result; a false/exception result cannot create fake LIVE/public authority
- publication backend failures become FAILED rather than successful receipts
- observability remains importable and truthful on platforms without the Unix `resource` module; unsupported process RSS is reported as unavailable
- `UpdateSettings` itself defaults to automatic checking OFF and automatic safe install OFF
- signed manifests marked `rollback_compatible=false` are refused by the automatic transactional installer until a non-rollback migration/recovery mechanism exists
- macOS self-update retains the old app until the newly launched app completes a local-only `/api/status` health handshake; failure restores/reopens the prior app
- macOS health handshakes refuse non-local destinations
- Settings rehydrates update channel/check/install values from saved server configuration, and the raw pre-hydration controls default visually to OFF

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
- real DAW audio capture, certified loudness/true-peak compliance, listening quality, and realtime performance; deterministic offline measurements are fixture-validated only
- native VST3 hosting or commercial-plugin characterization
- N0TE Bridge / native ARK / process-tap acceptance
- real Logic Pro, FL Studio, or Pro Tools DEEP integration
- signed/notarized consumer release acceptance on each target platform

## Deliberately not claimed in 1.2.4

- actual audio listening/AudioTap analysis pipeline
- Plugin Delta / Reference Delta / Finish Dry Run
- automatic arbitrary plugin-to-native parameter translation
- automatic licensed web sound import / Try in Song
- complete Music Map dependency/Chord Follower engine
- safe duplicate/take-lane generative MIDI transaction
- plugin sandbox / production native VST3 host
- Voice Lab / guide singer

## Real-Mac acceptance evidence — 2026-08-14

The first target-Mac/Live acceptance pass produced useful real-world evidence:

- Ableton initially did **not** show `Ableton_Live_MCP` because the configured Ableton User Library was wrong.
- After correcting the User Library setting, the Remote Script appeared in Live.
- After changing a Live setting and refreshing the Set in the N0TE UI, N0TE detected the updated Live state.

This proves the installed bridge/UI can communicate with the user's real Live environment when the correct User Library is configured. It also exposed a diagnostics gap: installation success alone does not prove that Live is using the same User Library path. `docs/ROADMAP.md` therefore keeps the disposable real-Live acceptance boundary explicit.

## Gate 1 implementation status

Gate 1 binds new transactions and simplification experiments to the stable ProjectStore song key, scopes recent context and Undo, rejects legacy/cross-Set ownership guesses, revalidates Apply and recovery targets, and serializes mutations. Review regressions prove Set-anchor-only Save As migration, same-process unrelated-Set isolation, stable-ID Undo after track index shifts, deterministic same-second transaction chronology, and fail-closed ambiguous simplification recovery without native Undo. Atomic state writes, proposal expiry, malformed/oversized request handling, 404/409/503 failure classes, consistent local Host/Origin rejection, and Remote Script diagnostics are automated-test covered.

The closure sweep proves execute-success is journaled before fallible post-observation, same-path/different-Set targetless Undo refusal, actual coerced post-state recovery, serialization of explicit native Undo, locked proposal registries and song-state read/modify/write, parent-directory fsync, and offline-safe/credential-complete/latest-outcome Doctor behavior. Set ownership requires the scoped N0TE song key plus a matching recorded/current Live Set-session identity; saved path, process token, signature, or raw index alone is insufficient.

The real-Live acceptance pass additionally caught and corrected a Doctor-only false negative: the pinned Remote Script is installed directly as `Remote Scripts/Ableton_Live_MCP/{__init__.py,bridge.py}`. The Doctor validates that actual installer/upstream layout rather than requiring an extra nested package directory.

The provider switchboard is transport-only. Gemini uses native structured output and handles malformed/incomplete candidates by isolating thought parts, checking finish metadata, discarding the bad candidate, and making at most one fresh schema-constrained retry. It never guess-repairs safety-critical JSON. This does not widen the Ableton action whitelist or bypass proposal validation, approval, mutation serialization, journaling, Set ownership, or N0TE Undo safety. Cloud-provider availability and local-model quality remain real-machine acceptance concerns.

The **Ableton Gate 1 safety scope is implementation complete / real-Live acceptance pending**. The wider N0TE product remains partially implemented; this is not a SONG-READY or whole-product-complete claim. The canonical next acceptance target remains the disposable-Set checklist in `CODEX_SONG_READY_HANDOFF.md`.

Reproducible dependency-free statement-coverage command: `bash scripts/coverage.sh`.

## Song-centered product workflow validation

The portable product layer persists session operating goals and evidence-only debriefs, distinguishes provenance/privacy and technical/creative evidence, queues unresolved ear decisions, creates loudness-matched offline audition comparisons without choosing taste, derives non-prescriptive Mix and Signal evidence, produces evidence-bound portability plans, and connects delivery authority to professional render receipts. The final review hardening keeps these workflows subordinate to evidence, explicit authority, recovery, and Artist taste. Native VST3, Bridge, ARK, real DAW migration/capture, certified audio conformance, and listening acceptance remain explicitly unverified.

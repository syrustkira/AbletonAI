# N0TE Ableton AI — Canonical Roadmap

This file owns build order. New ideas go to backlog unless they fix reliability, satisfy an existing gate, or a real music session exposes a blocking need.

## Gate 0 — Canonical source

Goal: one versioned project reality for ChatGPT, Codex and the user.

- [ ] GitHub contains the exact tested v1.2.4 baseline plus governance docs.
- [ ] Secrets/runtime state are excluded.
- [ ] CI runs canonical validation.
- [ ] `AGENTS.md`, blueprint, feature matrix and roadmap agree.

## Gate 1 — SONG-READY trust and safety

This gate is the blocker before using N0TE mutations on a real new song.

### Transaction ownership / recovery — P0

- [x] Bind every new transaction to `ProjectStore.song_key(snapshot)` and stable Set/session identity.
- [x] Store Set path when available, before/after signatures and affected target fingerprints.
- [x] Scope recent-transaction lookup to the current song.
- [x] Prevent another song's transaction from entering coproducer recent-change context.
- [x] Refuse cross-Set `Undo N0TE`.
- [x] Validate affected post-state before inverse execution.
- [x] Preserve safe partial-rollback behavior.
- [x] Preserve unsaved → saved continuity.
- [x] Legacy unscoped transactions remain visible but cannot be guessed into ownership.
- [x] Simplification experiment transactions obey the same rules.

### Apply/action revalidation — P0/P1

- [x] Re-run action validation against the fresh Apply snapshot.
- [x] Resolve stable target IDs as late as practical; reduce dependence on raw track indexes.
- [x] Use one canonical recursive Live-object index for selection and validation; exposed stable IDs are retained for execution/recovery.

### State/concurrency — P1

- [x] Introduce reusable atomic JSON writes for important state.
- [x] Fix stable lock ownership for context/project/library stores.
- [x] Serialize mutating operations.
- [x] Add concurrency/state-corruption regressions.

### Remote Script Doctor / HEALTH — P0/P1

- [x] Report manifest User Library and Remote Script path.
- [x] Detect missing/extra nested `Ableton_Live_MCP` folder structure.
- [x] Inspect latest Ableton `Log.txt` for Remote Script/import/traceback errors.
- [x] Detect “files installed but Live did not load script.”
- [x] Detect likely User-Library mismatch and provide repair guidance.
- [x] Verify bridge `127.0.0.1:8765`, companion `127.0.0.1:8766` and configured OpenAI credential state without exposing secrets.

### Server/API hardening — P1

- [x] Typed HTTP failure status codes.
- [x] Request-body size cap.
- [x] Consistent local Host/Origin policy.
- [x] Proposal expiration/garbage collection.
- [x] Redacted rotating diagnostic log.
- [x] Characterization tests before splitting overloaded server responsibilities.

### Song-Ready acceptance

A disposable Set must prove:

1. Remote Script visible/loads.
2. bridge + UI healthy.
3. current Set/selection read correctly.
4. song goal/intent persists.
5. read-only questions work.
6. small approved mutation targets correct Set/object.
7. stale proposal rejected.
8. same-Set Undo works.
9. cross-Set/incompatible Undo refused.
10. restart continuity works.
11. full automated suite passes.

**After Gate 1 passes, start the real song. Later gates must not delay music creation.**

## Gate 2 — Context Engine

- [ ] `ContextEnvelope` with context version, song key, repo commit, snapshot signature and last transaction ID.
- [ ] Provenance classes for user intent / Live fact / audio measurement / memory / inference.
- [ ] Context conflict detection.
- [ ] Delta-based context updates.
- [ ] Session distillation: objective / completed / kept / rejected / unresolved / next.
- [ ] `N0TE_SYNC_PACKET.json` generation.
- [ ] Decision ledger ties hypothesis → experiment → result → keep/reject.
- [ ] Selective retrieval rather than full-context dumping.

## Gate 3 — ChatGPT / MCP sync

- [ ] Read-only MCP adapter.
- [ ] `get_n0te_status`.
- [ ] `get_current_set`.
- [ ] `get_current_selection`.
- [ ] `get_song_context`.
- [ ] `get_recent_decisions`.
- [ ] `get_context_diff`.
- [ ] `search_n0te_context`.
- [ ] Secure remote/tunnel connection where supported.
- [ ] No mutation tools until the existing proposal/action pipeline is explicitly integrated and reviewed.

## Gate 4 — Audio Evidence

- [ ] AgentAudioTap real capture acceptance.
- [ ] Correct track/channel/sample validation.
- [ ] Peak/RMS/LUFS/crest metrics.
- [ ] Spectral-region metrics.
- [ ] low-end / low-mid density metrics.
- [ ] stereo correlation/width.
- [ ] silence and section-energy metrics.
- [ ] Before/After with level matching.
- [ ] Plugin Delta.
- [ ] Reference Delta.
- [ ] Finish Dry Run audio preflight.

## Gate 5 — Production intelligence

- [ ] Production Recipes over safe/native operations.
- [ ] Signal Flow graph/diagnostics.
- [ ] repair suggestions using evidence and native/owned tools first.
- [ ] portability/recovery orchestration.
- [ ] simplification verification using Audio Evidence.

## Gate 6 — Musical intelligence

- [ ] Music Map 2 sections/harmony/energy/dependencies.
- [ ] Chord Followers review/update/ignore flow.
- [ ] safe duplicate/take-lane MIDI experiments.
- [ ] constrained motif/rhythm/register/tension variation.

## Gate 7 — Discovery / plugin intelligence

- [ ] DISCOVER Try in Song with license/provenance checks.
- [ ] plugin sandbox/characterization where technically safe.
- [ ] explicit proven parameter mappings for substitution.
- [ ] Simplify/Substitute 2.0.

## Gate 8 — Longitudinal intelligence

- [ ] Session Debrief.
- [ ] evidence-based workflow pattern learning.
- [ ] catalog/A&R comparison after audio evidence exists.

## Gate 9 — Later

- [ ] authorized Voice Lab / guide singer.
- [ ] optional Extensions transport adapter.
- [ ] advanced generative audio only when real sessions prove the need.

## Permanent engineering rule

**No new N0TE feature category unless a real music session exposes the need, or it fixes reliability/safety.**

## Product distribution and host management

- [x] Shared **Detect DAWs** service recognizes Ableton Live, Logic Pro, FL Studio, and Pro Tools, retains multiple installations, and keeps detection separate from adapter support and Song identity.
- [x] First-run can finish healthily with no DAW, AI OFF, Network OFFLINE, no OBS, no camera, and no Local AI.
- [x] Component-aware updater supports stable/opt-in channels, NetworkPolicy pause, signed manifest and payload verification, minimal plans, host-close deferral, rollback, and offline `.n0teupdate` import.
- [x] Adapter updates report fixed, revalidation-required, and unchanged capabilities without suppressing healthy paths.
- [ ] Provision production release signing keys, private runtime payloads, native installer execution, and real-host compatibility evidence during external release acceptance.

## macOS consumer build preparation

- [x] Deterministic unsigned `N0TE Development.app` layout, configurable bundle identity, Info.plist, internal launcher, bundle hashes, notices, and DMG input staging.
- [x] Finder entrypoint, single-instance lock, first-run routing, platform-owned user data/log/cache/recovery/update paths, and non-destructive legacy-state copy.
- [x] macOS Info.plist DAW metadata backend, multi-install discovery, and non-terminating RUNNING / NOT_RUNNING / UNKNOWN process detector.
- [x] External self-update helper contract, startup health model, disposable Ableton checklist, and per-capability acceptance evidence store.
- [ ] Ingest an approved macOS CPython build input, build on real macOS, execute real DAW discovery/process checks, sign, notarize, staple, and complete disposable real-Ableton acceptance.

## Cross-platform audio and plugin closure

- [x] Platform-owned mutable paths distinguish macOS Application Support, Windows roaming/local AppData, and Linux XDG data/cache/state roots.
- [x] Deterministic offline analysis measures levels, DC, crest, spectral bands, dynamics, stereo/mono risk, and pairwise masking, with measurement separated from diagnosis and approval-required corrective previews.
- [x] ARK graph routes fail closed on implicit feedback cycles and report modeled latency without claiming measured realtime performance.
- [x] Metadata-only VST3/AU/CLAP/AAX discovery runs outside Core and plugin quarantine/semantic evidence is version scoped.
- [ ] Native plugin instantiation/rendering, certified BS.1770 loudness/true peak, realtime ARK backends, commercial-plugin characterization, listening acceptance, and real-platform packaging remain external/native acceptance work.

## Functional audio and native product pass

- [x] Decode PCM 16/24/32 and IEEE float32 WAV with explicit format rejection and source hashes.
- [x] Implement K-weighted, absolute/relative gated LUFS-I/M/S and LRA, configurable interpolated true peak, radix-2 FFT/STFT, reference and stem comparisons.
- [x] Implement offline N0TE DSP, bounded mastering candidates, explicit external-render authority, non-overwriting Song-linked receipts, and analysis history invalidation by source hash.
- [x] Compile and sanitizer-test native C11 DSP kernels and a bounded SPSC audio ring on Linux x86_64.
- [x] Execute Linux `.desktop` and `/proc` discovery and validate a private-runtime AppDir builder; add Windows Registry/process/mutex/installer sources.
- [x] Expose real offline Audio and isolated Plugins views; close the companion server's remaining direct runtime provider policy check.
- [ ] Official VST3 SDK ingestion and native VST3/Bridge builds are blocked by absent SDK and denied official-repository access; commercial-plugin and real-host evidence require installations.
- [ ] Certified loudness vectors, listening acceptance, PipeWire/JACK/ALSA runtime, real AppImage tooling, approved private runtime payloads, and target macOS/Windows builds remain external acceptance.

## Post-merge audio correctness

- [x] Plugin/Core reconnect rejection is atomic and cannot change Song/workspace identity; unspecified host compatibility fails closed.
- [x] Transparent Python/native floating-point DSP preserves headroom above 0 dBFS; only explicit clipper, limiter, and integer conversion stages constrain amplitude.
- [x] Add transfer/reference tests for gain, polarity, filters/EQ, compressor, gate, clipper, limiter, de-esser, and transient control.
- [x] Parse extensible WAV channel roles, exclude LFE from loudness, label unknown multichannel layout, add per-band stereo evidence and bounded streaming level/true-peak analysis.
- [x] Scope analysis history by Song/workspace/source/range/algorithm/settings; add PCM16/24/32/float rendering, explicit TPDF policy, rich receipts, and bounded deterministic mastering optimization.
- [x] Persist plugin registry/quarantine/mappings, separate module identity from install fingerprint, bind evidence to class/version/binary, and migrate schemas fail-safely.
- [ ] Native VST3 host remains blocked by absent official SDK and denied official repository access; no metadata-only behavior is promoted to hosting.

## Song-centered product integration pass

- [x] Persist bounded session goals, exit conditions, not-now guardrails, and evidence-only debriefs through the existing Song event history.
- [x] Represent universal evidence provenance/privacy, Technical/Creative Twin conflicts, and a durable Ear Decision queue including defer and cannot-tell outcomes.
- [x] Provide N0TE DSP audition comparison with optional loudness matching while keeping measurement winner separate from artist choice.
- [x] Derive Mix relationships without treating overlap as a defect, Signal diagnostics with modeled/measured latency labels, and evidence-bound portability plans without fake translation.
- [x] Connect professional RenderSpecification output authority to delivery receipts, version branches, archive manifests, monitoring context, and capability-granular health.
- [ ] Real listening acceptance, native VST3/Bridge/ARK execution, and real DAW migration remain dependent on legitimate SDKs, target hosts/platforms, audio devices, and human ears.

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

- [ ] Bind every new transaction to `ProjectStore.song_key(snapshot)` and stable Set/session identity.
- [ ] Store Set path when available, before/after signatures and affected target fingerprints.
- [ ] Scope recent-transaction lookup to the current song.
- [ ] Prevent another song's transaction from entering coproducer recent-change context.
- [ ] Refuse cross-Set `Undo N0TE`.
- [ ] Validate affected post-state before inverse execution.
- [ ] Preserve safe partial-rollback behavior.
- [ ] Preserve unsaved → saved continuity.
- [ ] Legacy unscoped transactions remain visible but cannot be guessed into ownership.
- [ ] Simplification experiment transactions obey the same rules.

### Apply/action revalidation — P0/P1

- [ ] Re-run action validation against the fresh Apply snapshot.
- [ ] Resolve stable target IDs as late as practical; reduce dependence on raw track indexes.
- [ ] Use one canonical recursive Live-object index for selection, validation and execution.

### State/concurrency — P1

- [ ] Introduce reusable atomic JSON writes for important state.
- [ ] Fix stable lock ownership for context/project/library stores.
- [ ] Serialize mutating operations.
- [ ] Add concurrency/state-corruption regressions.

### Remote Script Doctor / HEALTH — P0/P1

- [ ] Report manifest User Library and Remote Script path.
- [ ] Detect missing/extra nested `Ableton_Live_MCP` folder structure.
- [ ] Inspect latest Ableton `Log.txt` for Remote Script/import/traceback errors.
- [ ] Detect “files installed but Live did not load script.”
- [ ] Detect likely User-Library mismatch and provide repair guidance.
- [ ] Verify bridge `127.0.0.1:8765`, companion `127.0.0.1:8766` and configured OpenAI credential state without exposing secrets.

### Server/API hardening — P1

- [ ] Typed HTTP failure status codes.
- [ ] Request-body size cap.
- [ ] Consistent local Host/Origin policy.
- [ ] Proposal expiration/garbage collection.
- [ ] Redacted rotating diagnostic log.
- [ ] Characterization tests before splitting overloaded server responsibilities.

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

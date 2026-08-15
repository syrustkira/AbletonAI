# Codex Master Handoff — Complete N0TE After SONG-READY

## Purpose

This prompt owns the work that is intentionally **not** part of the Gate 1 SONG-READY handoff.

Do not use this prompt until:
1. the exact tested N0TE source is the repository baseline,
2. Gate 1 SONG-READY engineering is implemented,
3. automated validation is green,
4. the user has completed the real-Ableton SONG-READY acceptance checklist.

The objective is to complete the remaining canonical N0TE roadmap without allowing later features to weaken the trusted Action Plane or delay real music work unnecessarily.

---

# Deferred ideas inventory

## Gate 2 — Context Engine
Not implemented by SONG-READY:
- ContextEnvelope with context version, song key, repo commit, Live snapshot signature and last transaction ID
- provenance classes: explicit user intent, current Live fact, measured audio fact, memory, inference, unknown
- context conflict detection
- delta-based context updates
- session distillation
- N0TE_SYNC_PACKET.json
- hypothesis → experiment → result → keep/reject decision ledger
- selective retrieval instead of full-context dumping
- durable per-song API conversation/state where appropriate

## Gate 3 — ChatGPT / MCP sync
Not implemented by SONG-READY:
- real MCP server/adapter
- read-only tools:
  - get_n0te_status
  - get_current_set
  - get_current_selection
  - get_song_context
  - get_recent_decisions
  - get_context_diff
  - search_n0te_context
- secure remote/tunnel connection
- automatic context synchronization through MCP
- future write tools routed through N0TE proposal/approval/transaction/undo safety

## Gate 4 — Audio Evidence
Not implemented by SONG-READY:
- AgentAudioTap real capture pipeline
- correct track/channel/sample verification
- temporary audio storage/cleanup/recovery
- peak / true peak where applicable
- RMS
- LUFS
- crest factor
- spectral-region measurements
- low-end percentage
- low-mid density
- high-frequency energy
- stereo width/correlation
- silence detection
- section-energy/dynamics comparison
- Before/After capture
- level-matched A/B
- Plugin Delta
- Reference Delta
- Finish Dry Run audio preflight

## Gate 5 — Production intelligence
Not implemented by SONG-READY:
- Production Recipes over safe Ableton-native operations
- examples: kick→bass sidechain, parallel drum bus, shared room, vocal delay throws, reference-track setup, A/B copy, recording prep, commit/freeze/portable workflows
- Signal Flow graph
- routing / return / group / sidechain diagnostics
- repair suggestions based on evidence
- native/owned-tool-first repair choices
- portability/recovery orchestration
- simplification verification using measured Audio Evidence

## Gate 6 — Musical intelligence
Not implemented by SONG-READY:
- Music Map 2
- section model
- harmony / key / chord / energy / intent model
- dependency graph
- Chord Followers with review/update/ignore workflow
- safe duplicate/take-lane MIDI experiments
- preserve rhythm / pitch / motif / harmony / density constraints
- motif continuation
- call-and-response
- register/tension/rhythmic-density variation
- bass/chord/melody variation
- cycle-aware variations

## Gate 7 — Discovery and plugin intelligence
Not implemented by SONG-READY:
- DISCOVER Try in Song
- preview → license check → import → project/library copy → place → warp/pitch when appropriate → A/B → keep/reject
- provenance storage: creator/source/license/source URL/date/song/query/role
- Find / Similar / Complement / Replace ranking using song context
- plugin sandbox / characterization where technically safe
- owned-plugin capability database
- explicit plugin→native parameter mappings only where proven
- Simplify/Substitute 2.0
- audio-verified plugin replacement experiments

## Gate 8 — Longitudinal intelligence
Not implemented by SONG-READY:
- structured Session Debrief
- longitudinal workflow-pattern learning from evidence
- accepted/rejected production-pattern learning
- catalog comparison
- A&R ranking after audio evidence exists
- “what should I finish?” evidence-backed reasoning

## Gate 9 — Later / optional
Intentionally later:
- authorized Voice Lab / guide singer
- authorized rough-performance conversion
- vocal doubles / harmonies / alternate delivery
- optional Ableton Extensions transport adapter
- advanced generative audio/continuation/repaint only if real sessions justify it

## Additional backlog items retained from earlier design work
These must not be forgotten, but should be fitted into the gates above rather than becoming new parallel projects:
- installed Live version / edition / Max-for-Live capability detection
- expanded deterministic Ableton capability database with version/edition requirements
- native stems and audio-to-MIDI used as forensic/reconstruction tools where supported
- exhaustive capability lookup only where useful; do not duplicate the Ableton manual blindly
- model/cost routing for OpenAI calls when evidence shows it is needed
- plugin latency / portability / dependency / CPU kept as distinct complexity dimensions
- actual CPU measurement before making CPU-savings claims
- web discovery licensing/provenance before automated download or placement
- context provenance and privacy boundaries for unreleased music/user data
- Session Recovery Capsule for intent/decisions/provenance, not redundant .als backup infrastructure

---

# MASTER CODEX TASK

You are working on **N0TE Ableton AI**.

Your task is to complete the canonical post–SONG-READY roadmap in order, preserving all existing product, security, context, transaction and recovery invariants.

## FIRST: establish repository truth

Read:
1. `AGENTS.md`
2. `PROJECT_BLUEPRINT.md`
3. `docs/ROADMAP.md`
4. `FEATURE_MATRIX.json`
5. `N0TE_CONTEXT_PACK.json`
6. `BUILD_VALIDATION.md`
7. `HARDENING_AUDIT.md`
8. `CHANGELOG.md`
9. relevant tests and implementation files

Then:
- run `git status -sb`
- identify current branch and base commit
- run the canonical baseline validation
- confirm Gate 1 SONG-READY is actually implemented in code/tests
- inspect evidence for real-Live acceptance if it has been recorded

If Gate 1 is incomplete or repository state does not match the documented baseline:
**STOP feature implementation and report the blocker.**
Do not build later features on an unsafe baseline.

## Permanent invariants

Preserve these throughout all work:

### Knowledge Plane / Action Plane
Knowledge may be broad.
Actions remain narrow, validated, proposal-gated, reversible and journaled.

No new API, MCP tool, model call or subsystem may bypass:

`PROPOSE → VALIDATE → USER APPROVAL → REVALIDATE → EXECUTE → JOURNAL → REVIEW → UNDO`

### Truth model
Keep separate:
- current Live evidence
- explicit user intent
- captured audio measurements
- stored memory
- AI inference
- unknown/unverifiable state

Never present inference as measurement or Live fact.

### Native-first
Use:
`CURRENT SET → ABLETON NATIVE → OWNED TOOL/RACK → N0TE EXTENSION → EXTERNAL/WEB/NEW`

Do not rebuild strong Ableton mechanisms merely to own the feature.

### Safety
- every mutation belongs to a verifiable song/Set
- persistent writes remain atomic/backwards-compatible
- mutation paths must not race
- preserve originals for experiments
- fail closed when ownership/recovery cannot be proven
- no arbitrary Live/Python execution for normal AI
- never weaken validation merely to make a feature work

### Evidence
- no audio claim without captured audio
- no CPU-saving claim without CPU measurement
- no plugin equivalence claim without proven parameter/job mapping + listening/evidence
- measured difference is not automatically a problem

---

# Execution strategy

Do **not** implement Gates 2–9 as one giant undifferentiated refactor.

Work gate-by-gate.

For each gate:

1. Audit current implementation first.
2. Produce a concise implementation plan.
3. Identify dependencies and existing native Ableton functionality.
4. Add characterization/regression tests before risky refactors.
5. Implement the smallest complete vertical slice.
6. Expose it through the actual N0TE UI/chat where required.
7. Run focused tests.
8. Run the canonical full validation suite.
9. Update `FEATURE_MATRIX.json` and relevant docs to reflect only proven behavior.
10. Commit the gate as a coherent change.
11. Report:
   - implementation
   - tests
   - migrations
   - safety/privacy implications
   - real-Ableton acceptance still required
12. Only then proceed to the next gate if the current environment/task scope reasonably permits it.

If a gate requires real Ableton/macOS/audio acceptance that cannot be performed in Codex cloud:
- finish what can be deterministically implemented/tested,
- produce an exact real-machine acceptance checklist,
- mark the gate `implementation-complete / acceptance-pending`,
- do not falsely label it fully proven.

Do not delete or skip the remaining gates.

---

# Gate 2 — Context Engine

Implement a first-class context subsystem.

Required:
- typed/versioned ContextEnvelope
- five scopes: PRODUCT / USER / SONG / SESSION / LIVE
- provenance metadata
- conflict detection
- delta computation
- context versioning
- selective retrieval
- session distillation
- sync-packet generation
- decision-ledger integration
- backward-compatible migration from current state files

Requirements:
- raw conversation is history, not canonical memory
- current Live state is ephemeral evidence
- explicit current user intent supersedes stale preference memory for intent
- do not leak private/unreleased context into logs or public repo
- include unit/migration/conflict tests

---

# Gate 3 — MCP / ChatGPT synchronization

Build the MCP adapter only after Context Engine is stable.

Start READ-ONLY.

Expose:
- `get_n0te_status`
- `get_current_set`
- `get_current_selection`
- `get_song_context`
- `get_recent_decisions`
- `get_context_diff`
- `search_n0te_context`

Requirements:
- MCP is a narrow adapter over existing services, not a second N0TE architecture
- no normal write/mutation MCP tools yet
- authentication/privacy/tunnel configuration remains separate from private context
- health diagnostics show MCP state without secrets
- add protocol/integration tests

After read-only MCP is accepted, future mutation tools may be added only by routing through the existing proposal/approval/transaction/undo system.

---

# Gate 4 — Audio Evidence

Connect AgentAudioTap to an actual deterministic N0TE audio-analysis pipeline.

Required vertical path:
`CAPTURE → VERIFY TARGET → ANALYZE → STORE RESULT → COMPARE → CLEAN UP`

Start with deterministic measurements:
- peak
- RMS
- LUFS where technically appropriate
- crest factor
- spectral-region energy
- low-end share
- low-mid density
- stereo width/correlation
- silence
- section energy

Then:
- Before/After
- loudness/level matching
- Plugin Delta
- Reference Delta
- Finish Dry Run

Requirements:
- distinguish measured data from interpretation
- captured source/track must be verified
- temporary audio must have cleanup/recovery
- no audio-dependent feature can be marked complete until the user runs the real-Ableton acceptance checklist

---

# Gate 5 — Production Intelligence

Build deterministic high-value workflows over existing safe primitives.

Start with a small recipe registry and implement the most reusable recipes first:
- kick→bass sidechain
- parallel drum bus
- shared short room
- A/B/reference setup
- vocal recording prep / delay-throw scaffolding where supported
- portable/commit workflow where appropriate

Add:
- Signal Flow graph/diagnostics
- routing/return/group/sidechain visibility
- evidence-based repair suggestions
- simplification verification through Audio Evidence

Every recipe:
- preflights
- resolves targets
- previews operations
- requires approval
- executes as one transaction
- supports safe recovery

---

# Gate 6 — Musical Intelligence

Implement Music Map 2 and safe variation.

Music Map 2:
- sections
- key/scale
- chords
- musical function
- energy
- intent
- motifs
- dependencies

Chord Followers:
- identify potentially affected followers after harmony changes
- REVIEW / UPDATE / IGNORE
- never blindly rewrite the whole song

MIDI Variation:
- duplicate/take-lane or duplicate-clip experiment
- preserve original
- constrained transformations
- multiple alternatives where practical
- no destructive overwrite by default

Use native Ableton MIDI/probability/take-lane mechanisms first.

---

# Gate 7 — Discovery / Plugin Intelligence

Complete DISCOVER into an auditionable, provenance-safe workflow.

Implement:
- Find
- Similar
- Complement
- Replace
- Try in Song
- license/provenance validation
- import/place/warp/pitch experiment
- keep/reject memory

Plugin intelligence:
- safe capability characterization
- owned-tool database
- explicit parameter mappings only when proven
- plugin/native A/B using Audio Evidence
- Simplify/Substitute 2.0

Never claim equivalence from plugin category alone.

---

# Gate 8 — Longitudinal Intelligence

Implement:
- Session Debrief
- evidence-backed workflow-pattern learning
- accepted/rejected approach learning
- catalog comparisons
- A&R support after sufficient audio/project evidence exists

Avoid personality diagnosis.
Describe observable workflow patterns with supporting evidence.

---

# Gate 9 — Later

Only after earlier gates are stable:
- authorized Voice Lab / guide singer
- Extensions transport adapter
- advanced generative audio justified by real-session need

Voice features must operate only on the user's own or explicitly authorized voice material.

The Extensions adapter must preserve the LiveBridge contract rather than rewrite product logic.

---

# Final full-build audit

When all gates that can be implemented in the current environment are complete:

1. audit every roadmap item as:
   - DONE
   - IMPLEMENTED / REAL-LIVE ACCEPTANCE PENDING
   - PARTIAL
   - BLOCKED
   - INTENTIONALLY DEFERRED
2. verify docs match code
3. run canonical validation
4. run coverage
5. inspect mutation surfaces
6. inspect secret handling
7. inspect persistence migrations
8. inspect MCP boundaries
9. inspect audio truth labeling
10. produce one master REAL-LIVE ACCEPTANCE PLAN covering every Live/audio-dependent feature

Do not claim N0TE fully production-proven until those real-machine checks are completed.

## Final response format

Return:
1. gate-by-gate status
2. commits/branches/PRs created
3. files changed
4. tests and validation
5. schema/migrations
6. security/privacy implications
7. remaining real-Live checks
8. remaining intentional backlog
9. exact next user action

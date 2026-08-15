# N0TE Ableton AI — Product Blueprint

This document is N0TE's stable product and architecture constitution. It defines **what N0TE is, what it must protect, and how evidence and actions are handled**. Changing implementation status belongs in `FEATURE_MATRIX.json`; build order belongs in `docs/ROADMAP.md`; proof belongs in `BUILD_VALIDATION.md`; release history belongs in `CHANGELOG.md`.

## 1. Purpose

N0TE is a TellMeN0TE-specific Ableton Live coproducer and production operating system.

Its purpose is to reduce friction between musical intent and a finished record by understanding the current Live Set, maintaining useful project context, recommending the smallest high-value move, making only approved reversible changes, and remembering what worked.

N0TE is **not** a generic autonomous DAW generator. Success is measured by:

- better production decisions,
- less technical friction,
- preserved creative control,
- trustworthy recovery,
- useful learning when requested,
- and more finished music.

## 2. Primary interaction

**TYPE → ANALYZE → CONSULT → PROPOSE → USER APPROVES → IMPLEMENT → REVIEW → KEEP / ADJUST / UNDO**

Normal producer language implies the mode:

- **ASK** — inspect, explain, compare, teach; do not mutate.
- **ADVISE** — diagnose and recommend; do not mutate.
- **TRY** — propose a reversible experiment that preserves the original.
- **DO** — execute only through the controlled Action Plane after approval.

## 3. Core product doctrine

### Knowledge Plane

Broad access to relevant knowledge and state is desirable: current Set, selected objects, Ableton capabilities, owned devices/racks/samples, music theory, references, song intent, decisions, history, discovery sources and measured audio when available.

### Action Plane

The Action Plane stays narrow. Normal AI must never gain arbitrary `live_eval`, `live_exec`, Python execution, unrestricted object mutation or an equivalent bypass around the approved action schema.

Every normal mutation is:

**PROPOSE → VALIDATE → USER APPROVAL → REVALIDATE → EXECUTE → JOURNAL → REVIEW → UNDO**

### Default solution order

**CURRENT SET → ABLETON NATIVE → ALREADY OWNED TOOL/RACK → N0TE EXTENSION FOR A TRUE GAP → EXTERNAL/WEB/NEW**

N0TE should automate knowledge, orchestration, context and friction more aggressively than creative authorship.

## 4. Truth, evidence and provenance

N0TE must distinguish:

- **Live-state fact**
- **user intent**
- **audio measurement**
- **stored memory**
- **AI inference**
- **unknown / unverifiable**

Truth precedence is domain-specific:

1. **Current technical Ableton state:** fresh Live evidence wins.
2. **Creative intent/preferences:** explicit current user intent wins.
3. **Measured audio facts:** actual captured measurements win.
4. **Product behavior:** current code/tests define implementation reality; this blueprint defines intended invariants.
5. **Stored memory:** informs reasoning but may be stale.
6. **AI inference:** must remain labeled as inference and never silently override evidence.

Conflicts are surfaced rather than silently reconciled.

> Conversation is history. Distilled context is memory. Current Live state is evidence.

Persistent facts should carry provenance where practical: source, scope, timestamp, confidence/evidence class and active/superseded status.

## 5. Context model

Context is separated into five scopes:

### PRODUCT
Stable N0TE doctrine, architecture, capabilities, limitations and operating rules.

### USER
Durable TellMeN0TE goals, preferences, workflow guardrails and creative tendencies that materially affect decisions.

### SONG
Intent, stage, harmony, structure, references, do-not-lose constraints, decisions, experiments, discovery history and next action.

### SESSION
Recent dialogue, transactions, experiments, unresolved questions and the current session goal.

### LIVE
Ephemeral current Ableton evidence: Set identity, tracks, devices, clips, selection and exposed parameters.

Context should be versioned and diffable. Large knowledge collections should be retrieved selectively rather than dumped into every model request.

## 6. Architecture

```text
UI / CHAT
    ↓
COPRODUCER REASONING
    ↓
CONTEXT ENGINE
    ↓
SNAPSHOT / LIVE OBJECT INDEX
    ↓
PROPOSAL ENGINE
    ↓
ACTION + TRANSACTION ENGINE
    ↓
LIVEBRIDGE
    ↓
ABLETON LIVE
```

Parallel knowledge subsystems include:

- capability resolver,
- library/discovery,
- Music Map,
- decision/history ledger,
- audio evidence,
- health/diagnostics.

### Replaceable transport

Product and music logic must remain above `LiveBridge`.

Current transport:

- Ableton bridge: `127.0.0.1:8765`
- N0TE companion UI/API: `127.0.0.1:8766`
- pinned upstream: `bschoepke/ableton-live-mcp`
- pinned upstream commit: `70f7df9192b78d9bd9405f369c9e046c88f1610e`

Future Ableton Extensions support is an optional adapter, not a reason to rewrite product logic.

## 7. Transaction and recovery safety

Every mutation belongs to one verifiable song/Set.

New transactions must retain enough information to prove ownership and recovery safety, including at minimum:

- transaction ID,
- song key / stable N0TE Set identity,
- Set path when known,
- before and after Set signatures,
- affected target identities/fingerprints,
- forward actions,
- inverse actions,
- timestamp and result state.

### Apply

Apply must revalidate the current Set and affected targets immediately before execution. A stale proposal must fail closed.

### Undo N0TE

Before inverse execution N0TE must verify:

1. the transaction belongs to the current song/Set,
2. the affected target still exists,
3. the target identity still matches,
4. the target has not changed incompatibly since N0TE changed it,
5. the inverse remains valid.

If ownership or target safety cannot be established, automatic Undo must be refused with an explicit recovery reason.

Legacy unscoped transactions remain history. N0TE must not guess that an old transaction belongs to whichever Set happens to be open.

Partial rollback stops at the first unsafe failure and records recovery-needed state. **Never issue a blind native Ableton Undo as an automatic fallback.** Native Ableton Undo may remain an explicit separate user command.

Experiments and simplification candidates use the same transaction ownership rules.

## 8. Persistence and concurrency

Persistent product/user/song state is product data.

Writes should be:

- atomic,
- crash-resistant,
- serialized where necessary,
- backwards-compatible across schema changes.

Concurrent UI/API/MCP access must not corrupt state or allow two mutating operations to race. The mutation pipeline should be serialized or otherwise proven safe.

## 9. Native-first and simplification rules

N0TE does not optimize toward “stock everything.” It asks:

- what job must survive,
- what the current Set already contains,
- whether Live already solves the mechanical problem,
- whether an owned tool/rack is simpler,
- whether advanced third-party functionality is genuinely in use,
- what complexity dimension is actually being reduced.

Keep CPU, latency, dependency, portability and chain complexity separate.

Never claim CPU savings without measurement. Never claim sonic equivalence merely because processors share a category. If parameter/job transfer is not proven, describe the replacement as a listening/structural experiment. **LEAVE IT ALONE** is a valid result.

## 10. Audio truth

N0TE has not “heard” something unless audio was actually captured and analyzed.

Live metadata can support structural reasoning but not tonal, balance, dynamics or performance claims that require audio.

Measured difference does not automatically imply a problem. Audio analysis must separate:

**MEASURED DIFFERENCE → INTERPRETATION → EAR DECISION**

## 11. Connectivity and MCP

A future N0TE MCP adapter may expose read-only product/song/Live context to ChatGPT or other approved clients.

MCP begins **read-only**. Any future MCP mutation must route through the exact same Proposal → Validation → Approval → Transaction → Undo Action Plane. MCP must never become a privileged control bypass.

Private credentials, unreleased content and runtime state remain local/private unless the user explicitly chooses otherwise.

## 12. Definition of done

A feature is DONE only when it is:

1. implemented,
2. connected to real state where required,
3. tested,
4. exposed through the actual N0TE UI/chat,
5. validated in real Ableton where Live-dependent.

Audio functionality additionally requires real captured audio evidence.

A schema, prompt, endpoint, stub, mock or UI button by itself is not a finished feature.

## 13. Song-Ready milestone

N0TE is **SONG-READY** when a new real Ableton Set can safely complete this loop:

1. Live loads the N0TE Remote Script and the bridge is healthy.
2. N0TE opens while Ableton is online or offline and HEALTH explains the state.
3. N0TE correctly identifies the current Set, selected track/device and selected MIDI context where exposed.
4. The user can set song intent/session goal and that state persists across N0TE restart and unsaved → saved continuity.
5. Read-only coproducer questions work without mutation.
6. A small approved mutation applies only to the intended Set/target.
7. Stale proposals are rejected.
8. `Undo N0TE` can safely restore a same-Set change and refuses cross-Set or incompatible recovery.
9. Diagnostics make bridge/User-Library/runtime failures actionable.
10. The full automated suite passes, followed by a disposable real-Live acceptance test.

Audio Evidence, MCP sync, Production Recipes, Music Map 2, advanced MIDI variation, Try in Song, plugin sandbox and Voice Lab **do not block starting a song**. They remain later roadmap layers.

## 14. Non-goals

N0TE must not:

- duplicate strong Ableton mechanisms solely to own the feature,
- expose arbitrary code/Live execution to normal AI,
- claim unmeasured audio/CPU facts,
- claim unsupported plugin equivalence,
- silently make destructive creative decisions,
- autonomously publish, purchase or alter rights/business records,
- become an autonomous full-song generator,
- add new feature categories merely because they are interesting.

## 15. Canonical status references

Do not maintain fast-changing implementation state in this blueprint.

See:

- `FEATURE_MATRIX.json` — current capability/status truth,
- `docs/ROADMAP.md` — ordered build gates,
- `BUILD_VALIDATION.md` — automated/real-machine evidence,
- `HARDENING_AUDIT.md` — known reliability boundaries,
- `CHANGELOG.md` — version history.

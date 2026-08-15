# Codex Handoff — Make N0TE Song-Ready

Use the prompt below as the next bounded Codex assignment. The objective is not to complete every future roadmap feature. It is to make the current v1.2.4 coproducer trustworthy enough for the first real new-song session.

---

You are working on **N0TE Ableton AI**.

## Mission

Bring the current v1.2.4 baseline through **Gate 1 — SONG-READY trust and safety** in `docs/ROADMAP.md` without adding later roadmap features.

When complete, the user should be able to create a fresh Ableton Set, use N0TE to read the Set, maintain song/session context, ask production questions, apply a small approved change and safely undo it without risk of another Set's transaction being applied.

Do **not** implement Audio Evidence, MCP, Production Recipes, Music Map 2, advanced MIDI generation, Try in Song, plugin sandbox or Voice Lab in this task.

## Read first

Read in this order:

1. `AGENTS.md`
2. `PROJECT_BLUEPRINT.md`
3. `docs/ROADMAP.md`
4. `FEATURE_MATRIX.json`
5. `N0TE_CONTEXT_PACK.json`
6. `BUILD_VALIDATION.md`
7. `HARDENING_AUDIT.md`
8. `INSTALLER_AUDIT.md`

Then inspect the current implementation and tests before editing.

## Source-of-truth rule

- Code/tests establish current implementation behavior.
- Blueprint establishes intended invariants.
- Feature matrix establishes current feature status.
- Roadmap establishes priority/order.

If these disagree, report the drift. Do not silently choose or rewrite unrelated architecture.

## Preflight — no edits until this is complete

1. Run `git status -sb` and identify the branch/base commit.
2. Confirm the repository contains the exact v1.2.4 application/installer/test baseline rather than only governance docs.
3. Run the current full automated suite and record baseline results.
4. Inspect at minimum:
   - transaction creation/storage/lookup,
   - `apply_proposal`, `undo_last_n0te`, simplification experiment transactions,
   - `ProjectStore.song_key` and unsaved → saved migration,
   - action validation/target resolution,
   - persistent JSON writes/locks,
   - HTTP request handling,
   - installer/health User Library logic.
5. Produce a concise preflight report with current behavior, affected files, invariants, risks and tests to add.

After preflight, implement Gate 1.

# Workstream A — P0 transaction ownership and Undo safety

## Problem

Current transaction storage/lookup is effectively global. A transaction from Set A must never be treated as the latest transaction for Set B, injected into Set B's coproducer context, or automatically undone while Set B is open.

## Required invariant

**A transaction may affect only the song/Set that created it.**

Every newly created transaction must record sufficient ownership and recovery information, including:

- `transaction_id` / existing ID,
- `song_key`,
- stable N0TE Set/session identity as available from ProjectStore,
- Set file path when known,
- `set_signature_before`,
- `set_signature_after`,
- affected target identities/fingerprints or equivalent post-state evidence,
- timestamps.

### Lookup/context

- Make recent/latest transaction lookup song-scoped.
- `ask_openai()` must not include another song's `RECENT N0TE CHANGE`.
- History may remain globally inspectable, but operational lookup defaults to current-song scope.

### Apply

- Revalidate every proposed action against the fresh Apply snapshot immediately before inverse capture/execution.
- Preserve stale whole-Set proposal rejection.
- Prefer stable target IDs over raw indexes where the bridge exposes them; resolve indexes only at execution boundaries when unavoidable.

### Undo N0TE

Before inverse execution verify:

1. transaction ownership matches current song/Set,
2. target still exists,
3. target identity still matches,
4. affected target has not changed incompatibly after the N0TE change,
5. inverse remains valid.

Do not require the entire Set to be unchanged if unrelated user edits can safely coexist. Validate affected targets specifically.

If ownership/safety cannot be proven: **fail closed** with a useful reason.

### Unsaved → saved continuity

N0TE already maintains continuity when an unsaved Set is saved. Transactions from that continuing song must remain associated after legitimate save migration.

### Legacy transactions

- Preserve old records.
- Do not guess ownership.
- Legacy/unscoped records may remain visible in history but automatic Undo must be refused when ownership cannot be established.

### Partial rollback

Preserve existing behavior: stop after the first inverse failure/unsafe state; record recovery-needed information; never trigger blind native Ableton Undo automatically.

### Simplification experiments

Use the same ownership and recovery rules for experiment-track transactions.

## Required regression tests

At minimum:

A. Set A mutation → switch Set B → `Undo N0TE` refused.
B. Set A mutation → switch Set B → Set A recent transaction absent from Set B model context.
C. Set A Apply → same Set Undo → succeeds.
D. N0TE mutation → unrelated manual Set edit → targeted Undo still succeeds if affected target is unchanged.
E. N0TE mutation → affected target manually changed → unsafe inverse refused/recovery state returned.
F. unsaved Set → N0TE mutation → Save As continuity → transaction still belongs to same song and can be safely undone.
G. legacy unscoped transaction visible but never automatically assigned to arbitrary current Set.
H. simplification experiment obeys cross-Set ownership rules.
I. existing partial rollback behavior remains passing.

# Workstream B — Live object targeting consistency

Create or consolidate one canonical recursive object-index path used by selection awareness, validation and mutation targeting so nested Rack devices that N0TE can see are not rejected merely because another subsystem only indexed top-level devices.

Do not broaden the action whitelist.

# Workstream C — state safety / concurrency

The server is threaded. Harden persistent state before adding MCP or more callers.

- Create a reusable atomic JSON-write helper for important state.
- Use stable store-owned locks rather than temporary per-call locks.
- Audit ProjectStore, context, library, transactions/proposals and decision/discovery/checkpoint writes.
- Serialize normal mutating Apply/Undo/experiment operations with a stable mutation lock or otherwise prove they cannot race.
- Add focused concurrency/atomic-write regression tests without redesigning the entire application.

# Workstream D — Remote Script Doctor / HEALTH

The first real-Mac acceptance test found a wrong User Library configuration. Once the correct User Library was selected, Ableton showed `Ableton_Live_MCP` and N0TE detected a changed Live setting after UI refresh.

Turn this into deterministic diagnostics.

HEALTH/doctor should report without exposing secrets:

- manifest User Library,
- expected Remote Script path,
- required Remote Script files/folder nesting,
- whether bridge `127.0.0.1:8765` responds,
- whether N0TE `127.0.0.1:8766` is healthy,
- OpenAI credential configured/not configured,
- latest Ableton `Log.txt` path when discoverable,
- relevant `Ableton_Live_MCP`, RemoteScript, traceback/import/module/syntax errors,
- a distinct state for “files installed but Live did not load the script,”
- likely User-Library mismatch with clear repair instructions.

Do not make a heuristic look like proof. Label what is verified versus inferred.

# Workstream E — HTTP/server hardening required for Song-Ready

Without a broad rewrite:

- add meaningful HTTP status codes for malformed input, unknown route/proposal, stale conflict, Ableton/OpenAI unavailable and unexpected failure,
- cap request-body size,
- apply local Host/Origin protections consistently,
- add proposal TTL/cleanup,
- add redacted rotating diagnostics suitable for support,
- do not log API keys or full sensitive model/audio payloads.

If `n0te_server.py` needs decomposition, first add characterization tests and extract only coherent services needed to complete this gate. Avoid a speculative architecture rewrite.

# Workstream F — tests/CI and documentation truth

- Define one canonical test/coverage command so coverage numbers are reproducible.
- Cover server failure paths, standalone health and uninstall logic where practical.
- Add CI for Python tests/compile, shell syntax, JSON validation and UI JavaScript syntax when Node is available.
- Update `FEATURE_MATRIX.json`, `BUILD_VALIDATION.md`, `HARDENING_AUDIT.md` and docs only to reflect behavior actually implemented/proven.
- Do not mark SONG-READY until the automated acceptance criteria are green.

# Validation

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

Run the repository's JavaScript syntax validation if available.

# Completion criteria

Do not claim completion merely because tests pass.

Return a **REAL-LIVE ACCEPTANCE CHECKLIST** for the user using a disposable Set:

1. select correct User Library,
2. restart Live and confirm `Ableton_Live_MCP`,
3. run HEALTH/doctor,
4. verify selected normal/return/master track and selected device,
5. enter song intent/session goal and restart N0TE to verify persistence,
6. ask read-only current-Set question,
7. create/apply small rename or pan proposal,
8. make an unrelated manual change and verify safe targeted N0TE Undo,
9. create another N0TE change, manually alter its affected target and verify Undo refuses unsafe recovery,
10. create transaction in disposable Set A, switch to disposable Set B and verify cross-Set Undo is refused,
11. verify stale proposal rejection,
12. test unsaved → Save As continuity.

Only after the user passes this checklist may Gate 1 be marked real-Live accepted.

# Final report

Return:

1. preflight findings,
2. root causes fixed,
3. files changed,
4. migrations/schema changes,
5. tests added,
6. complete validation results,
7. security/safety implications,
8. documentation/status changes,
9. anything still requiring real macOS/Ableton acceptance,
10. exact user acceptance checklist,
11. next recommended bounded task from `docs/ROADMAP.md` **without implementing it**.

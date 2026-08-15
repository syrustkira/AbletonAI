# N0TE Ableton AI — Agent Engineering Contract

This repository contains a safety-sensitive Ableton Live coproducer. Read this file before editing.

## Read first

1. `PROJECT_BLUEPRINT.md`
2. `docs/ROADMAP.md`
3. `FEATURE_MATRIX.json`
4. `N0TE_CONTEXT_PACK.json`
5. `BUILD_VALIDATION.md`
6. `HARDENING_AUDIT.md`

## Product invariants

- N0TE is a coproducer and production operating system, not an autonomous DAW generator.
- Primary UX: TYPE → ANALYZE → CONSULT → PROPOSE → USER APPROVES → IMPLEMENT → REVIEW → KEEP / ADJUST / UNDO.
- Knowledge Plane may be broad; Action Plane must remain narrow, validated, proposal-gated and reversible.
- Normal AI must never receive arbitrary `live_eval`, `live_exec`, Python execution or unrestricted Live mutation.
- Default solution order: CURRENT SET → ABLETON NATIVE → ALREADY OWNED TOOL/RACK → N0TE EXTENSION FOR TRUE GAP → EXTERNAL/WEB/NEW.
- Preserve originals for experiments. Fail closed when ownership, target identity or recovery safety cannot be proven.
- Never claim audio was heard unless audio was actually captured and analyzed.
- Never claim CPU savings without measurement.
- Never claim plugin equivalence from category alone.
- Do not duplicate strong native Ableton mechanisms merely to own the feature.

## Truth, state and safety precedence

- Derive current implementation behavior from code and tests, not prose alone.
- If documentation and implementation disagree, report the drift.
- Do not silently rewrite architecture to match accidental implementation.
- Explicit current user intent defines creative intent.
- Fresh Live snapshots define current Ableton technical state.
- Captured measurements define measured audio facts.
- AI inference must remain labeled as inference.
- Persistent state mutations should be atomic and backwards-compatible.
- Every Ableton mutation transaction must belong to a verifiable song/Set.
- Legacy state whose ownership cannot be proven must fail closed rather than be guessed.
- Concurrent mutation paths must be serialized or otherwise proven safe.

## Mutation pipeline

Every normal mutation must preserve:

`PROPOSE → VALIDATE → USER APPROVAL → REVALIDATE → EXECUTE → JOURNAL → REVIEW → UNDO`

No MCP, API, UI or future adapter may bypass this pipeline.

## Engineering discipline

- Inspect existing implementation/tests before editing.
- Make the smallest coherent change that completely solves the task.
- Add regression tests that fail against the old behavior.
- Do not add unrelated feature categories.
- Do not loosen validation to make tests pass.
- Preserve persistent user/song/context state across migrations.
- Keep product/music logic above `LiveBridge` so transport remains replaceable.
- Treat real Ableton/macOS acceptance separately from mocked/automated tests.

## Canonical validation

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

Also run repository JavaScript syntax validation and permanent CI checks where available.

## Completion reporting

Report:
- root cause/problem
- files changed
- behavior changed
- tests added
- complete validation results
- state/schema compatibility
- security/safety implications
- documentation drift/status changes
- real Ableton/macOS checks still required

Do not claim a Live-dependent feature fully proven from mocks alone.

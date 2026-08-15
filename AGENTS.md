# N0TE Ableton AI — Agent Instructions

This repository is the canonical source of truth for N0TE Ableton AI. Before architectural or behavioral changes, read:

1. `PROJECT_BLUEPRINT.md`
2. `FEATURE_MATRIX.json`
3. `N0TE_CONTEXT_PACK.json`
4. `BUILD_VALIDATION.md`
5. `HARDENING_AUDIT.md`
6. `docs/ROADMAP.md`

## Product doctrine

1. N0TE exists to help TellMeN0TE finish records. Do not turn it into a generic DAW generator.
2. Primary loop: TYPE → ANALYZE → CONSULT → PROPOSE → USER APPROVES → IMPLEMENT → REVIEW → KEEP / ADJUST / UNDO.
3. Infer ASK / ADVISE / TRY / DO from normal producer language.
4. Knowledge Plane may be broad; Action Plane must stay small, validated, approval-gated and reversible.
5. Normal AI must never expose arbitrary `live_eval`, `live_exec`, Python or equivalent unrestricted mutation.
6. Prefer CURRENT SET → ABLETON NATIVE → OWNED TOOL/RACK → N0TE EXTENSION → EXTERNAL/WEB/NEW.
7. Do not rebuild strong native Ableton mechanisms when orchestration/context is the real gap.
8. Never claim sonic equivalence by category.
9. Never claim CPU savings without measurement.
10. “Leave it alone” is valid.
11. Preserve originals during experiments.
12. Audio claims require actual captured audio evidence.
13. Do not add a feature category merely because it is interesting. Complete the canonical roadmap.

## Source-of-truth and drift rules

- Code and tests establish current implementation behavior.
- `PROJECT_BLUEPRINT.md` establishes intended architecture/invariants.
- `FEATURE_MATRIX.json` establishes current feature status.
- `docs/ROADMAP.md` establishes build order.
- Files under `app/context/` that mirror canonical root/governance files are packaging mirrors, not independent authorities. Update the canonical source and its packaged mirror together; `tests/test_context_mirrors.py` must remain green.
- If implementation and documentation disagree, report the drift. Do not silently rewrite architecture to match an accidental implementation and do not claim documentation proves behavior.

## Truth and state precedence

- Fresh Live evidence defines current technical Ableton state.
- Explicit current user intent defines creative intent/preferences.
- Captured measurements define measured audio facts.
- Stored context may be stale and must not silently override newer evidence.
- AI inference must remain labeled as inference.
- Conflicts should be surfaced.

## Architecture boundaries

- Keep product/music logic above `LiveBridge`.
- Ableton bridge endpoint: `127.0.0.1:8765`.
- N0TE companion UI endpoint: `127.0.0.1:8766`.
- Persistent user state lives under `~/.n0te-ableton-ai` and must not be committed.
- Installer updates remain transactional: failed update restores previous working N0TE; uninstall restores pre-N0TE state only when trustworthy manifest evidence exists.
- Never put credentials in source or Git history.

## Mutation invariant

Any code capable of changing Ableton must preserve:

**PROPOSE → VALIDATE → USER APPROVAL → REVALIDATE → EXECUTE → JOURNAL → REVIEW → UNDO**

Every N0TE transaction must belong to a verifiable song/Set. Legacy ownership that cannot be proven must fail closed rather than be guessed.

MCP or another interface may not bypass this invariant.

## Persistence/concurrency

- Treat user/song/context/history as product data.
- Prefer atomic writes (temporary file + replace) for important JSON/state.
- Use stable locks; do not create throwaway locks that fail to synchronize with other callers.
- Serialize mutating operations or prove concurrency safety.
- Preserve backwards-compatible state migration.

## Definition of done

A feature is not DONE merely because a schema, prompt, endpoint or UI button exists. It must be implemented, connected to real state where required, tested, exposed through actual product UX, and real-Live accepted where Live-dependent. Audio claims require real captured audio.

## Change discipline

Before editing:

1. inspect `git status`,
2. run relevant baseline tests,
3. inspect current implementation/tests,
4. identify invariants and failure modes,
5. keep the change bounded.

Do not:

- modify unrelated work,
- opportunistically redesign adjacent systems,
- loosen validation to make tests pass,
- invent audio evidence,
- silently break persistent-state compatibility,
- modify pinned third-party source/attribution without an explicit dependency update,
- bump the release version unless the release is actually being cut.

Regression fixes require tests that fail on the old behavior.

## Validation before completion

Run the relevant subset plus the full suite where practical:

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

If Node is available, syntax-check the JavaScript in `app/static/index.html` using the existing validation approach.

Never claim mocked tests prove actual Ableton/macOS/plugin behavior.

## Completion report

For substantial tasks report:

1. root cause/current behavior,
2. files changed,
3. behavior changed,
4. tests added,
5. complete validation results,
6. persistent-state/schema compatibility,
7. security/safety implications,
8. documentation drift found/updated,
9. what still requires real Ableton/macOS acceptance,
10. recommended next bounded task without implementing it.

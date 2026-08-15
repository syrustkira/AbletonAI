# N0TE Ableton AI — Changelog

## Unreleased — canonicalization / Song-Ready planning

Documentation/governance only; no runtime behavior is claimed changed by this entry.

- Reframed `PROJECT_BLUEPRINT.md` as stable architecture/product doctrine instead of mixing roadmap and release history.
- Added explicit truth/provenance hierarchy and context scopes.
- Added transaction ownership/recovery invariant identified during v1.2.4 code review.
- Added a concrete SONG-READY milestone so later roadmap features do not block making music.
- Added `AGENTS.md` engineering contract for Codex/agents.
- Added canonical `docs/ROADMAP.md` with reliability-first gate order.
- Recorded real-Mac acceptance evidence: after correcting the Ableton User Library setting, `Ableton_Live_MCP` became visible and N0TE detected a changed Live setting after UI refresh.
- Identified follow-up defects for the next code release: cross-Set transaction/Undo scoping, stronger User Library/Remote Script diagnostics, state concurrency/atomicity and server integration coverage.

## 1.2.4

Audited macOS bootstrap/installer lifecycle hardening. See `INSTALLER_AUDIT.md`, `BUILD_VALIDATION.md` and `HARDENING_AUDIT.md`.

## 1.2.1–1.2.3

Correctness, context persistence, packaging and Python/bootstrap installer hardening. Historical details remain in the audits and earlier release artifacts.

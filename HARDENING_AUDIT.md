# v1.2.1 Hardening Audit

This file exists to keep the distinction between **fixed**, **truthfully partial**, and **planned** visible inside the artifact.

## Fixed in 1.2.1

- Unsaved Set memory no longer keys itself directly from mutable `set_signature`.
- Unsaved semantic state migrates to the saved-path identity when continuity is established.
- Persistent context no longer blocks a newer shipped context forever.
- User context overrides are separate from the managed shipped base and legacy differing context is archived before replacement.
- Local coproducer conversation is stored per song and survives companion restart.
- Selected return/master track device awareness is supported where Live exposes `Track.View.selected_device`.
- Device inventory can recurse through Rack chains; deep traversal is demand-driven to control latency.
- Natural-language discovery requests are normalized before Browser/web searching and can carry simple negative constraints.
- Partial N0TE rollback stops safely; no blind native Undo fallback.
- Failed fatal installer upgrades restore the previous app/Remote Script in the tested simulated failure path.
- FINISH no longer treats structural readiness as proven bounce readiness.
- Simplification UI/runtime explicitly labels automatic builds as structural A/B candidates with default replacement settings.
- Capability resolver explicitly reports that its deterministic catalog is curated, not exhaustive.

## Still partial by design

- Simplify/replace analysis can identify jobs/candidates, but arbitrary plugin state cannot yet be translated into a native equivalent automatically.
- DISCOVER searches and previews/links providers, but does not yet safely download, provenance-store and place a selected web sound into the Set.
- Music Map remains structural + user chord context, not a full chord dependency engine.
- Existing-note MIDI editing is reversible; duplicate/take-lane variation generation remains future work.
- Server integration coverage is much better but still the primary testing gap.

## Still planned, not placeholders pretending to work

- AgentAudioTap capture -> deterministic audio metrics
- Before/After + Plugin Delta
- Reference Delta
- Finish Dry Run audio preflight
- Production Recipes
- plugin sandbox/characterization
- Music Map dependency/chord followers
- authorized Voice Lab / guide vocals
- optional future Extensions transport adapter

## Installer lifecycle hardening in 1.2.4

- Recommended first-run installer no longer depends on preinstalled Python.
- Python prerequisite checksum and expected Python Software Foundation signer are verified.
- Bootstrap preserves failure exit codes through cleanup traps.
- Python HTTPS certificate setup is completed/verified before N0TE network operations.
- Apple/Xcode Python and active virtual environments are not chosen as persistent runtimes.
- Nonstandard Ableton User Library is remembered across updates and can be selected graphically when missing.
- Pinned bridge archive rejects path traversal and verifies the core `bridge.py` Git blob.
- Update rollback backups and pre-N0TE uninstall backups are now separate concepts.
- Successful uninstall restores pre-N0TE files, archives the install manifest, and does not resurrect the previous N0TE version.
- Installed uninstaller is available without retaining the downloaded bundle.
- Manifest-driven uninstall uses an allowlist and refuses backup sources outside N0TE's backup directory.
- Project/upstream license files are preserved with the installed source/components.
- Installed HEALTHCHECK resolves the User Library from the current install manifest, so custom locations remain consistent after install.
- Obsolete rollback-only snapshots are removed after a newer update succeeds; pre-N0TE restore backups remain intact for uninstall.
- Companion `/api/status` now returns app/config/context/library status while Ableton is offline instead of collapsing to a generic connection error.

## Post-v1.2.4 real-acceptance / code-review findings

These findings were discovered after the original 1.2.4 installer audit. Gate 1 implementation status is now recorded explicitly; real-Live proof is still pending:

1. **User Library diagnostics — implemented / real-Live acceptance pending:** HEALTH reports manifest/expected paths, exact nesting, required files, local endpoints, credential configuration, latest discoverable Live log evidence, installed-but-not-loaded state, labeled mismatch inference and repair guidance.
2. **Transaction ownership / cross-Set Undo — implemented / real-Live acceptance pending:** new edits and experiments carry stable song ownership, paths/signatures/target evidence; operational lookup is song-scoped and recovery revalidates current affected state.
3. **Threaded-state hardening — implemented:** important JSON paths use atomic replacement and stable path/store locks; Apply, N0TE Undo and experiment construction share one mutation lock.
4. **Server integration coverage — improved, still a continuing quality target:** 84 tests cover scoping, same-path/different-Set refusal, stable-ID recovery after index shifts, transaction chronology, journal-before-observation, actual coerced post-state, mutation/proposal/song-state serialization, atomic durable replacement, offline/latest-outcome Doctor behavior, proposal TTL, malformed/oversized bodies, 404/409/503 classifications, local Host/Origin rejection, and ambiguous simplification recovery without native Undo. Metadata-only rotating diagnostics are implemented.

See `docs/ROADMAP.md` Gate 1 and `CODEX_SONG_READY_HANDOFF.md` for the bounded next implementation scope.

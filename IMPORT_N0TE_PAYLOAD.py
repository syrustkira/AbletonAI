#!/usr/bin/env python3
"""One-shot importer for the validated N0TE Song-Ready baseline.

This file is temporary migration scaffolding. The GitHub Actions import workflow
removes it after a successful verified import.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parent
IMPORT_DIR = ROOT / ".n0te-import"
EXPECTED_SHA256 = "47d65f374701143ab54b222e00a53c61a64df5c1d76e33b47757f9d3bd378713"
EXPECTED_FILES = {
    "AGENTS.md",
    "PROJECT_BLUEPRINT.md",
    "FEATURE_MATRIX.json",
    "N0TE_CONTEXT_PACK.json",
    "CODEX_SONG_READY_HANDOFF.md",
    "CODEX_N0TE_FULL_BUILD_AFTER_SONG_READY.md",
    "docs/ROADMAP.md",
    "app/n0te_server.py",
    "tests/test_core.py",
}


def safe_member_path(name: str) -> Path:
    normalized = name.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    posix = PurePosixPath(normalized)
    if posix.is_absolute() or not normalized or any(part in {"..", ""} for part in posix.parts):
        raise RuntimeError(f"Unsafe archive member: {name!r}")
    if posix.parts[0] == ".git":
        raise RuntimeError("Archive must never write .git")
    return ROOT.joinpath(*posix.parts)


def extract_tar_xz(payload: bytes) -> None:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as tf:
        members = tf.getmembers()
        for member in members:
            target = safe_member_path(member.name)
            # Only ordinary files/directories are expected in the canonical source.
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(f"Unsupported archive member type: {member.name!r}")
            target_resolved = target.resolve()
            if ROOT.resolve() not in target_resolved.parents and target_resolved != ROOT.resolve():
                raise RuntimeError(f"Archive member escapes repo: {member.name!r}")

        for member in members:
            target = safe_member_path(member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                raise RuntimeError(f"Could not read archive member: {member.name!r}")
            with src, target.open("wb") as dst:
                dst.write(src.read())
            os.chmod(target, member.mode & 0o777)


def main() -> None:
    chunks = sorted(IMPORT_DIR.glob("archive-*.b64"))
    expected_names = [f"archive-{i:03d}.b64" for i in range(7)]
    actual_names = [p.name for p in chunks]
    if actual_names != expected_names:
        raise RuntimeError(f"Expected chunks {expected_names}, found {actual_names}")

    encoded = "".join("".join(p.read_text(encoding="ascii").split()) for p in chunks)
    payload = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"Payload SHA-256 mismatch: expected {EXPECTED_SHA256}, got {digest}")

    extract_tar_xz(payload)

    missing = sorted(path for path in EXPECTED_FILES if not (ROOT / path).is_file())
    if missing:
        raise RuntimeError(f"Import incomplete; missing required files: {missing}")

    print(f"Verified and imported N0TE payload SHA-256 {digest}")
    print(f"Required-file check passed ({len(EXPECTED_FILES)} files)")


if __name__ == "__main__":
    main()

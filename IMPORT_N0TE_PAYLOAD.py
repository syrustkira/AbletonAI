#!/usr/bin/env python3
"""One-shot importer for the validated N0TE v1.2.4 canonical source.

Temporary migration scaffolding. The payload is reconstructed from independently
Base64-encoded chunks, verified against the exact canonical archive SHA-256,
extracted safely, and then removed by the migration workflow after validation.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent
IMPORT_DIR = ROOT / ".n0te-import"
CHUNKS = [IMPORT_DIR / f"archive-{i:03d}.b64" for i in range(13)]
EXPECTED_PAYLOAD_SHA256 = "3a1dd19c4f3cd0f3f00e159fa4d782fdc42af1035c93cfee84088bae4c8dfb92"
EXPECTED_FILE_COUNT = 45


def decode_payload() -> bytes:
    missing = [p.name for p in CHUNKS if not p.is_file()]
    if missing:
        raise RuntimeError(f"Missing canonical payload chunks: {missing}")

    parts: list[bytes] = []
    for path in CHUNKS:
        encoded = "".join(path.read_text(encoding="ascii").split())
        parts.append(base64.b64decode(encoded, validate=True))

    payload = b"".join(parts)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_PAYLOAD_SHA256:
        raise RuntimeError(
            "Canonical payload SHA-256 mismatch: "
            f"expected {EXPECTED_PAYLOAD_SHA256}, got {digest}"
        )
    return payload


def safe_relative(name: str) -> Path:
    normalized = name.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    posix = PurePosixPath(normalized)
    if not normalized or posix.is_absolute() or any(part in {"", ".."} for part in posix.parts):
        raise RuntimeError(f"Unsafe archive member: {name!r}")
    if posix.parts[0] == ".git":
        raise RuntimeError("Archive may not write .git")
    return Path(*posix.parts)


def extract_verified_payload(payload: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as tf:
        members = tf.getmembers()
        regular_files = [m for m in members if m.isfile()]
        if len(regular_files) != EXPECTED_FILE_COUNT:
            raise RuntimeError(
                f"Canonical archive file count mismatch: expected {EXPECTED_FILE_COUNT}, "
                f"found {len(regular_files)}"
            )

        for member in members:
            rel = safe_relative(member.name)
            target = (destination / rel).resolve()
            base = destination.resolve()
            if target != base and base not in target.parents:
                raise RuntimeError(f"Archive member escapes extraction root: {member.name!r}")
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(f"Unsupported archive member type: {member.name!r}")

        for member in members:
            rel = safe_relative(member.name)
            target = destination / rel
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                raise RuntimeError(f"Could not read archive member: {member.name!r}")
            with src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            os.chmod(target, member.mode & 0o777)


def install_source(source: Path) -> None:
    files = sorted(p for p in source.rglob("*") if p.is_file())
    if len(files) != EXPECTED_FILE_COUNT:
        raise RuntimeError(
            f"Extracted source file count mismatch: expected {EXPECTED_FILE_COUNT}, found {len(files)}"
        )
    for src in files:
        rel = src.relative_to(source)
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> None:
    payload = decode_payload()
    with tempfile.TemporaryDirectory(prefix="n0te_canonical_import_") as tmp_text:
        source = Path(tmp_text)
        extract_verified_payload(payload, source)
        install_source(source)

    print(f"Verified canonical archive SHA-256: {EXPECTED_PAYLOAD_SHA256}")
    print(f"Installed canonical source files: {EXPECTED_FILE_COUNT}")


if __name__ == "__main__":
    main()

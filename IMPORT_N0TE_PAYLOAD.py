#!/usr/bin/env python3
"""One-shot canonical N0TE v1.2.4 source importer.

Temporary migration scaffolding. It accepts only a historical payload whose
extracted 45-file source matches the locally validated canonical SHA-256
manifest. The workflow adds the four GitHub/governance files separately and
removes this importer plus .n0te-import after successful validation.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
IMPORT_DIR = ROOT / ".n0te-import"

EXPECTED_SHA256 = {
    "AGENTS.md": "3e5ef20b4ce22eeaf3c45139d9a1d14fa117ecd471050e592ab51bf570413e17",
    "BUILD_VALIDATION.md": "55e0176d7e13da830d0243415266ce807cc7e9ec6da0a74b76a115b95e6923f6",
    "CHANGELOG.md": "cae51fbff379d6a5b915b5f0f5663bc561e90f4803ea25049810afeccd357c19",
    "CODEX_SONG_READY_HANDOFF.md": "48c50649562b6988d0ab7bcd39f506f97062adadfac7c5e8628ef4b27a0786e6",
    "FEATURE_MATRIX.json": "5b2a5e0650fe73592db5171b7026df2a0caf95121a5759836a1cee615838afb4",
    "HARDENING_AUDIT.md": "c0b21827bc39fb4fdf60d962dd18650b9579ee04b7621006cc3020508890ed1f",
    "INSTALLER_AUDIT.md": "4962393eb787f6ca44a0da177bda183f7100f8c8b8ab8b9594aa69ac261ef6e0",
    "INSTALL_N0TE_ABLETON_AI.py": "aff8546382b7538c79c8442a913e962089b444af84409b91940ee74177c11460",
    "INSTALL_N0TE_MAC.command": "d231baa31956cf8c14ccbb265737cba01d552ddaf960041e3b447c85455d01a6",
    "LICENSE": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
    "MODIFICATIONS.md": "2f9724a47ea6ab7d16ea19a749da89ccac2e2556b51f42969858d8071e92ae9d",
    "N0TE_CONTEXT_PACK.json": "4a5c56bf95b0dc4ca4a2dc1760f562a775e5249b9d4763aa2010742bacaec046",
    "PROJECT_BLUEPRINT.md": "8b91231136ba784cd9935ec2086ec6b0c97641d653cc5bcea249fad866b613fb",
    "README_FIRST.md": "585384f6cd190ca6cab5775f52c3279d73d148ee03bc9fbbd617191394473cef",
    "START_N0TE_ABLETON_AI.command": "b260efb3d889c243265fee9cb8904be37adca3abeaf0b80005a19d884870d23a",
    "THIRD_PARTY.md": "241864d77f929f969c8977152d08a42f209ef7edf66458a7dd5b56ad96ecb88a",
    "UNINSTALL_N0TE_ABLETON_AI.command": "cd54973a5909ff5f613e7663fc3857313efd35dc6673a867c33632660430e76e",
    "VERSION.json": "93885efcef29f0d074045543ac81420a9d4fbadefe01555acef07c9d038737a0",
    "app/context/BUILD_VALIDATION.md": "55e0176d7e13da830d0243415266ce807cc7e9ec6da0a74b76a115b95e6923f6",
    "app/context/FEATURE_MATRIX.json": "5b2a5e0650fe73592db5171b7026df2a0caf95121a5759836a1cee615838afb4",
    "app/context/HARDENING_AUDIT.md": "c0b21827bc39fb4fdf60d962dd18650b9579ee04b7621006cc3020508890ed1f",
    "app/context/INSTALLER_AUDIT.md": "4962393eb787f6ca44a0da177bda183f7100f8c8b8ab8b9594aa69ac261ef6e0",
    "app/context/LICENSE-GPL-3.0.txt": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
    "app/context/N0TE_CONTEXT.md": "8eb1b0405ca2e6c2c1c05766c7b2fff30fecb082d81c6cb287a7b29e39df6991",
    "app/context/N0TE_CONTEXT_PACK.json": "4a5c56bf95b0dc4ca4a2dc1760f562a775e5249b9d4763aa2010742bacaec046",
    "app/context/PROJECT_BLUEPRINT.md": "8b91231136ba784cd9935ec2086ec6b0c97641d653cc5bcea249fad866b613fb",
    "app/context/README_FIRST.md": "585384f6cd190ca6cab5775f52c3279d73d148ee03bc9fbbd617191394473cef",
    "app/context/ROADMAP.md": "ea9695de32839e426cb8bad58f2d666cc558a31acb7690b5030a00b12ff3cb28",
    "app/context/THIRD_PARTY.md": "241864d77f929f969c8977152d08a42f209ef7edf66458a7dd5b56ad96ecb88a",
    "app/context/ableton-live-mcp-LICENSE.txt": "8bcd1eb355d86769304d5bb80513fd09b3dece773001838b8a2edf7e8e3cf50a",
    "app/healthcheck.py": "950e10b8b1d80af4b23aaa93b6d536ec8ee3d070c88aa8b3b75cbef6e1059009",
    "app/n0te_bridge.py": "fc92ba3c2de629086361ed692ca1752d9acd3f47a74fa6f0ff723f3146e084a0",
    "app/n0te_context.py": "f6f012ea6519bd190d97bc95a54eecdea6d4a0a80790270da9c388d11a734f8d",
    "app/n0te_core.py": "3ac0c276c42efe79295f5a31608317cb9ffb899d988dda3f7acd42200c58e5f3",
    "app/n0te_discovery.py": "cf86b97ece1fd1634171cfc1795d64fcc03b485cc34ac29bdd2f8cd3db1ed99f",
    "app/n0te_library.py": "4b656a4ccd2ea5c068935b990c70e11dd2b2e26b8c2a064429db695fa20dbc70",
    "app/n0te_project.py": "9a86211479b34b1a1b22edaefc7c913efea25b319ebbf535a949d11b9ff5e88a",
    "app/n0te_server.py": "fb4681081fe33efc49e06e562cb070d69373f98ad8a151363c07c0737bbbd2e2",
    "app/n0te_uninstall.py": "bd4d48b8939a377226765e94c2568a6269f0206d1d540252db2bb362ea0560bf",
    "app/static/index.html": "56e357fe434119ada6b8b13152e9b9da6b678e2aba479840cc03621e6ed04ce1",
    "docs/ROADMAP.md": "ea9695de32839e426cb8bad58f2d666cc558a31acb7690b5030a00b12ff3cb28",
    "tests/test_core.py": "a417285c8052de17323f3441c18e588d603548b6908d40591b772745ae298279",
    "tests/test_mac_bootstrap.py": "9e5dacdc57198fecd2173c3a681fe39353fa000295c32c2a193ca9fa8818c8fd",
    "tests/test_python_installer.py": "eadaba1a9c7687a0731b127b2ad8e88c2262f25935ab6478f970393a80ff5b22",
    "third_party/ableton-live-mcp-LICENSE.txt": "8bcd1eb355d86769304d5bb80513fd09b3dece773001838b8a2edf7e8e3cf50a"
}


def candidate_sets() -> list[tuple[str, list[str]]]:
    candidates = [("archive", [f"archive-{i:03d}.b64" for i in range(7)])]
    for part3 in (["baseline-003.b64"], ["baseline-003a.b64", "baseline-003b.b64"]):
        for part5 in (["baseline-005.b64"], ["baseline-005a.b64", "baseline-005b.b64"]):
            candidates.append((
                "baseline:" + "+".join(part3 + part5),
                ["baseline-000.b64", "baseline-001.b64", "baseline-002.b64"]
                + list(part3)
                + ["baseline-004.b64"]
                + list(part5)
                + ["baseline-006.b64", "baseline-007.b64"],
            ))
    candidates.append(("payload", [f"payload-{i:03d}.b64" for i in range(3)]))
    return candidates


def safe_relative(name: str) -> Path:
    normalized = name.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    posix = PurePosixPath(normalized)
    if not normalized or posix.is_absolute() or any(part in {"", ".."} for part in posix.parts):
        raise RuntimeError(f"unsafe archive member {name!r}")
    if posix.parts[0] == ".git":
        raise RuntimeError("archive may not contain .git")
    return Path(*posix.parts)


def safe_target(base: Path, name: str) -> Path:
    rel = safe_relative(name)
    target = (base / rel).resolve()
    base_resolved = base.resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise RuntimeError(f"archive member escapes extraction root: {name!r}")
    return target


def extract_zip(payload: bytes, destination: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"ZIP CRC failure at {bad!r}")
        for info in zf.infolist():
            target = safe_target(destination, info.filename)
            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if file_type == stat.S_IFLNK:
                raise RuntimeError(f"symlink not allowed in payload: {info.filename!r}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            permissions = mode & 0o777
            if permissions:
                os.chmod(target, permissions)


def extract_tar(payload: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as tf:
        members = tf.getmembers()
        for member in members:
            target = safe_target(destination, member.name)
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(f"unsupported tar member type: {member.name!r}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                raise RuntimeError(f"could not read tar member: {member.name!r}")
            with src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            os.chmod(target, member.mode & 0o777)


def extract_payload(payload: bytes, destination: Path) -> None:
    if zipfile.is_zipfile(io.BytesIO(payload)):
        extract_zip(payload, destination)
        return
    try:
        extract_tar(payload, destination)
    except tarfile.TarError as exc:
        raise RuntimeError("payload is neither a valid ZIP nor supported tar archive") from exc


def locate_source_root(extracted: Path) -> Path:
    anchors = [p.parent for p in extracted.rglob("AGENTS.md") if p.is_file()]
    matches = []
    for base in anchors:
        if all((base / rel).is_file() for rel in EXPECTED_SHA256):
            matches.append(base)
    unique = []
    for base in matches:
        resolved = base.resolve()
        if resolved not in [p.resolve() for p in unique]:
            unique.append(base)
    if len(unique) != 1:
        raise RuntimeError(f"expected exactly one canonical source root, found {len(unique)}")
    return unique[0]


def verify_source(source: Path) -> None:
    mismatches = []
    for rel, expected in EXPECTED_SHA256.items():
        path = source / rel
        if not path.is_file():
            mismatches.append(f"missing {rel}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append(f"hash mismatch {rel}: {actual}")
    if mismatches:
        preview = "; ".join(mismatches[:5])
        if len(mismatches) > 5:
            preview += f"; ... {len(mismatches) - 5} more"
        raise RuntimeError(preview)


def decode_candidate(names: list[str]) -> bytes:
    missing = [name for name in names if not (IMPORT_DIR / name).is_file()]
    if missing:
        raise RuntimeError("missing chunks: " + ", ".join(missing))
    # Historical migration chunks were encoded independently. Decode every
    # chunk before concatenating binary bytes; concatenating padded Base64
    # text is invalid and was the root cause of the failed importer.
    parts = []
    for name in names:
        encoded = "".join((IMPORT_DIR / name).read_text(encoding="ascii").split())
        parts.append(base64.b64decode(encoded, validate=True))
    return b"".join(parts)


def install_source(source: Path) -> None:
    for rel in EXPECTED_SHA256:
        src = source / rel
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> None:
    failures = []
    for label, names in candidate_sets():
        try:
            payload = decode_candidate(names)
            payload_digest = hashlib.sha256(payload).hexdigest()
            with tempfile.TemporaryDirectory(prefix="n0te_verified_import_") as tmp_text:
                extracted = Path(tmp_text)
                extract_payload(payload, extracted)
                source = locate_source_root(extracted)
                verify_source(source)
                install_source(source)
            print(f"Verified canonical N0TE source from candidate {label}")
            print(f"Payload SHA-256: {payload_digest}")
            print(f"Canonical file-manifest verification passed: {len(EXPECTED_SHA256)}/45")
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with open(summary, "a", encoding="utf-8") as fh:
                    fh.write(f"## N0TE import verified\n- Candidate: `{label}`\n- Canonical files: {len(EXPECTED_SHA256)}/45\n- Payload SHA-256: `{payload_digest}`\n")
            return
        except Exception as exc:
            failures.append(f"{label} => {type(exc).__name__}: {exc}")
            print(f"Candidate {label} rejected: {type(exc).__name__}: {exc}")

    detail = " | ".join(failures)
    message = "No historical import payload matched the canonical v1.2.4 file manifest. " + detail
    print(f"::error title=N0TE canonical import failed::{message}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## N0TE import failed\n```text\n" + detail + "\n```\n")
    raise RuntimeError(message)


if __name__ == "__main__":
    main()

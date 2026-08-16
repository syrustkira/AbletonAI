import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_audio import AudioBuffer
from n0te_dsp import Limiter


def load_update_helper():
    path = ROOT / "scripts" / "macos_update_helper.py"
    spec = importlib.util.spec_from_file_location("n0te_macos_update_helper_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def app_fixture(path: Path, payload: bytes):
    target = path / "Contents" / "payload"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


class FollowupHardeningTests(unittest.TestCase):
    def test_limiter_preserves_complete_tail_with_positive_lookahead(self):
        source = AudioBuffer(1000, ((0.0, 0.0, 0.2, 0.5, 0.9),), "tail")
        limiter = Limiter(-1.0, lookahead_ms=2.0)
        output = limiter.process(source)
        self.assertEqual(len(output.channels[0]), len(source.channels[0]))
        self.assertGreater(abs(output.channels[0][-1]), 0.0)
        self.assertTrue(limiter.offline_latency_compensated)
        self.assertEqual(limiter.latency_frames, 2)

    def test_macos_update_rolls_back_when_new_app_never_becomes_healthy(self):
        helper = load_update_helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current, staged, backup = root / "N0TE.app", root / "Staged.app", root / "Backup.app"
            app_fixture(current, b"old")
            staged_file = app_fixture(staged, b"new")
            handoff = root / "handoff.json"
            handoff.write_text(json.dumps({
                "current_app": str(current),
                "staged_app": str(staged),
                "backup_app": str(backup),
                "pid": 123,
                "timeout": 1,
                "health_url": "http://127.0.0.1:8766/api/status",
                "bundle_hashes": {"Contents/payload": hashlib.sha256(staged_file.read_bytes()).hexdigest()},
            }), encoding="utf-8")
            completed = subprocess.CompletedProcess(["open"], 0)
            with patch.object(helper, "wait_for_exit", return_value=True), \
                 patch.object(helper, "wait_for_health", side_effect=RuntimeError("unhealthy")), \
                 patch.object(helper.subprocess, "run", return_value=completed), \
                 patch.object(sys, "argv", [str(ROOT / "scripts/macos_update_helper.py"), "--handoff", str(handoff)]):
                with self.assertRaisesRegex(RuntimeError, "unhealthy"):
                    helper.main()
            self.assertEqual((current / "Contents/payload").read_bytes(), b"old")
            self.assertFalse(current.with_name(current.name + ".old").exists())

    def test_macos_update_deletes_old_bundle_only_after_health_success(self):
        helper = load_update_helper()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current, staged, backup = root / "N0TE.app", root / "Staged.app", root / "Backup.app"
            app_fixture(current, b"old")
            staged_file = app_fixture(staged, b"new")
            handoff = root / "handoff.json"
            handoff.write_text(json.dumps({
                "current_app": str(current),
                "staged_app": str(staged),
                "backup_app": str(backup),
                "pid": 123,
                "timeout": 1,
                "health_url": "http://127.0.0.1:8766/api/status",
                "bundle_hashes": {"Contents/payload": hashlib.sha256(staged_file.read_bytes()).hexdigest()},
            }), encoding="utf-8")
            completed = subprocess.CompletedProcess(["open"], 0)
            with patch.object(helper, "wait_for_exit", return_value=True), \
                 patch.object(helper, "wait_for_health", return_value=True) as health, \
                 patch.object(helper.subprocess, "run", return_value=completed), \
                 patch.object(sys, "argv", [str(ROOT / "scripts/macos_update_helper.py"), "--handoff", str(handoff)]):
                self.assertEqual(helper.main(), 0)
            health.assert_called_once()
            self.assertEqual((current / "Contents/payload").read_bytes(), b"new")
            self.assertFalse(current.with_name(current.name + ".old").exists())

    def test_macos_health_handshake_rejects_nonlocal_destination(self):
        helper = load_update_helper()
        with self.assertRaisesRegex(RuntimeError, "local HTTP"):
            helper.wait_for_health("https://example.com/health", 0.1)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "INSTALL_N0TE_ABLETON_AI.py"

spec = importlib.util.spec_from_file_location("n0te_python_installer", INSTALLER_PATH)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PythonInstallerTests(unittest.TestCase):
    def test_successful_update_cleans_previous_rollback_only_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            previous = installer.BACKUPS
            installer.BACKUPS = Path(td) / "backups"
            try:
                old = installer.BACKUPS / "old_version"
                old.parent.mkdir(parents=True, exist_ok=True)
                old.write_text("old", encoding="utf-8")
                manifest = {"rollback_backups": [{"original": str(installer.INSTALL_ROOT), "backup": str(old)}]}
                warnings = installer.cleanup_old_rollback_backups(manifest)
                self.assertEqual(warnings, [])
                self.assertFalse(old.exists())
            finally:
                installer.BACKUPS = previous

    def test_version(self):
        self.assertEqual(installer.APP_VERSION, "1.2.4")

    def test_parser_defaults_to_install(self):
        args = installer.parser().parse_args([])
        self.assertEqual(args.command, "install")

    def test_parser_supports_management_commands(self):
        for command in ("install", "update", "uninstall", "health", "start"):
            self.assertEqual(installer.parser().parse_args([command]).command, command)

    def test_resolve_user_library_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            found = installer.resolve_user_library(td)
            self.assertEqual(found, Path(td).resolve())

    def test_transaction_rollback_restores_backup(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            old_backups = installer.BACKUPS
            installer.BACKUPS = td / "backups"
            try:
                target = td / "target"
                target.mkdir()
                (target / "old.txt").write_text("old", encoding="utf-8")
                tx = installer.InstallTransaction("test")
                tx.backup(target)
                target.mkdir()
                (target / "new.txt").write_text("new", encoding="utf-8")
                tx.touch(target)
                tx.rollback()
                self.assertTrue((target / "old.txt").is_file())
                self.assertFalse((target / "new.txt").exists())
            finally:
                installer.BACKUPS = old_backups

    def test_manifest_marks_python_installer_and_interpreter(self):
        with tempfile.TemporaryDirectory() as td:
            tx = installer.InstallTransaction("test")
            manifest = tx.manifest(Path(td), "skipped")
            self.assertEqual(manifest["installer"], "python")
            self.assertEqual(manifest["version"], "1.2.4")
            self.assertEqual(manifest["manifest_schema"], 2)
            self.assertTrue(manifest["python_executable"])

    def _sandbox_globals(self, td):
        td = Path(td)
        values = {
            "HOME": installer.HOME,
            "INSTALL_ROOT": installer.INSTALL_ROOT,
            "STATE": installer.STATE,
            "BACKUPS": installer.BACKUPS,
            "MANIFEST": installer.MANIFEST,
            "download": installer.download,
            "unpack_upstream": installer.unpack_upstream,
            "copy_app": installer.copy_app,
            "choose_user_library_gui": installer.choose_user_library_gui,
        }
        installer.HOME = td / "home"
        installer.HOME.mkdir()
        installer.INSTALL_ROOT = installer.HOME / "Library" / "Application Support" / installer.APP_NAME
        installer.STATE = installer.HOME / ".n0te-ableton-ai"
        installer.BACKUPS = installer.STATE / "backups"
        installer.MANIFEST = installer.STATE / "install_manifest.json"
        installer.choose_user_library_gui = lambda: None
        return values

    def _restore_globals(self, values):
        for key, value in values.items():
            setattr(installer, key, value)

    def _fake_upstream(self, _archive, destination):
        upstream = destination / f"ableton-live-mcp-{installer.UPSTREAM_COMMIT}"
        remote = upstream / "Ableton_Live_MCP"
        remote.mkdir(parents=True)
        (remote / "__init__.py").write_text("# fake bridge", encoding="utf-8")
        (remote / "bridge.py").write_text("# fake bridge body", encoding="utf-8")
        (upstream / "LICENSE").write_text("MIT fake", encoding="utf-8")
        scripts = upstream / "scripts"
        scripts.mkdir()
        (scripts / "build_agent_audio_tap.py").write_text("raise SystemExit(0)", encoding="utf-8")
        return upstream

    def test_resolve_user_library_reuses_manifest_path(self):
        with tempfile.TemporaryDirectory() as td:
            values = self._sandbox_globals(td)
            try:
                userlib = Path(td) / "Custom Ableton Library"
                userlib.mkdir()
                installer.STATE.mkdir()
                installer.MANIFEST.write_text(json.dumps({"ableton_user_library": str(userlib)}), encoding="utf-8")
                self.assertEqual(installer.resolve_user_library(), userlib.resolve())
            finally:
                self._restore_globals(values)

    def test_full_sandbox_install_and_uninstall(self):
        with tempfile.TemporaryDirectory() as td:
            values = self._sandbox_globals(td)
            try:
                userlib = Path(td) / "User Library"
                userlib.mkdir()
                installer.download = lambda _url, dest, attempts=3: dest.write_bytes(b"fake")
                installer.unpack_upstream = self._fake_upstream
                args = installer.parser().parse_args([
                    "install", "--user-library", str(userlib), "--no-audio-tap"
                ])
                self.assertEqual(installer.install(args), 0)
                remote = userlib / "Remote Scripts" / "Ableton_Live_MCP"
                self.assertTrue((remote / "__init__.py").is_file())
                self.assertTrue((remote / "LICENSE").is_file())
                self.assertTrue((installer.INSTALL_ROOT / "n0te_server.py").is_file())
                self.assertTrue((installer.INSTALL_ROOT / "n0te_uninstall.py").is_file())
                self.assertTrue((installer.INSTALL_ROOT / "launchers" / "UNINSTALL_N0TE.command").is_file())
                manifest = json.loads(installer.MANIFEST.read_text(encoding="utf-8"))
                self.assertEqual(manifest["installer"], "python")
                self.assertEqual(manifest["version"], "1.2.4")
                self.assertEqual(installer.uninstall(args), 0)
                self.assertFalse(remote.exists())
                self.assertFalse(installer.INSTALL_ROOT.exists())
                self.assertFalse(installer.MANIFEST.exists())
                self.assertTrue((installer.STATE / "last_uninstalled_manifest.json").is_file())
            finally:
                self._restore_globals(values)

    def test_full_install_failure_restores_previous_app_and_remote(self):
        with tempfile.TemporaryDirectory() as td:
            values = self._sandbox_globals(td)
            try:
                userlib = Path(td) / "User Library"
                remote = userlib / "Remote Scripts" / "Ableton_Live_MCP"
                remote.mkdir(parents=True)
                (remote / "old.txt").write_text("old remote", encoding="utf-8")
                installer.INSTALL_ROOT.mkdir(parents=True)
                (installer.INSTALL_ROOT / "old.txt").write_text("old app", encoding="utf-8")
                installer.download = lambda _url, dest, attempts=3: dest.write_bytes(b"fake")
                installer.unpack_upstream = self._fake_upstream

                def fail_copy():
                    raise RuntimeError("simulated copy failure")
                installer.copy_app = fail_copy

                args = installer.parser().parse_args([
                    "install", "--user-library", str(userlib), "--no-audio-tap"
                ])
                with self.assertRaises(RuntimeError):
                    installer.install(args)
                self.assertEqual((remote / "old.txt").read_text(encoding="utf-8"), "old remote")
                self.assertEqual((installer.INSTALL_ROOT / "old.txt").read_text(encoding="utf-8"), "old app")
            finally:
                self._restore_globals(values)

    def test_update_then_uninstall_restores_pre_n0te_files_not_previous_n0te(self):
        with tempfile.TemporaryDirectory() as td:
            values = self._sandbox_globals(td)
            try:
                userlib = Path(td) / "User Library"
                remote = userlib / "Remote Scripts" / "Ableton_Live_MCP"
                remote.mkdir(parents=True)
                (remote / "foreign.txt").write_text("pre-n0te remote", encoding="utf-8")
                installer.INSTALL_ROOT.mkdir(parents=True)
                (installer.INSTALL_ROOT / "foreign.txt").write_text("pre-n0te app", encoding="utf-8")
                installer.download = lambda _url, dest, attempts=3: dest.write_bytes(b"fake")
                installer.unpack_upstream = self._fake_upstream
                args = installer.parser().parse_args([
                    "install", "--user-library", str(userlib), "--no-audio-tap", "--no-desktop-shortcuts"
                ])

                self.assertEqual(installer.install(args), 0)
                first = json.loads(installer.MANIFEST.read_text(encoding="utf-8"))
                self.assertGreaterEqual(len(first["restore_backups"]), 2)

                self.assertEqual(installer.install(args), 0)
                second = json.loads(installer.MANIFEST.read_text(encoding="utf-8"))
                self.assertGreaterEqual(len(second["rollback_backups"]), 2)
                self.assertEqual(installer.uninstall(args), 0)

                self.assertEqual((remote / "foreign.txt").read_text(encoding="utf-8"), "pre-n0te remote")
                self.assertEqual((installer.INSTALL_ROOT / "foreign.txt").read_text(encoding="utf-8"), "pre-n0te app")
                self.assertFalse((installer.INSTALL_ROOT / "n0te_server.py").exists())
            finally:
                self._restore_globals(values)

    def test_unpack_upstream_rejects_wrong_bridge_blob(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td_text:
            td = Path(td_text)
            archive = td / "upstream.zip"
            prefix = f"ableton-live-mcp-{installer.UPSTREAM_COMMIT}"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(f"{prefix}/Ableton_Live_MCP/bridge.py", "not the pinned bridge")
                zf.writestr(f"{prefix}/Ableton_Live_MCP/__init__.py", "")
                zf.writestr(f"{prefix}/scripts/build_agent_audio_tap.py", "")
                zf.writestr(f"{prefix}/LICENSE", "MIT")
            dest = td / "out"
            dest.mkdir()
            with self.assertRaisesRegex(RuntimeError, "content verification failed"):
                installer.unpack_upstream(archive, dest)

    def test_uninstall_refuses_backup_source_outside_n0te_backup_directory(self):
        with tempfile.TemporaryDirectory() as td:
            values = self._sandbox_globals(td)
            try:
                userlib = Path(td) / "User Library"
                userlib.mkdir()
                remote = userlib / "Remote Scripts" / "Ableton_Live_MCP"
                outside = Path(td) / "outside.txt"
                outside.write_text("do not move", encoding="utf-8")
                installer.STATE.mkdir()
                installer.MANIFEST.write_text(json.dumps({
                    "ableton_user_library": str(userlib),
                    "touched_paths": [],
                    "restore_backups": [{"original": str(remote), "backup": str(outside)}],
                }), encoding="utf-8")
                args = installer.parser().parse_args(["uninstall"])
                self.assertEqual(installer.uninstall(args), 1)
                self.assertTrue(outside.is_file())
                self.assertTrue(installer.MANIFEST.is_file())
            finally:
                self._restore_globals(values)


if __name__ == "__main__":
    unittest.main()

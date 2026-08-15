import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import n0te_doctor


class DoctorRemoteScriptLayoutTests(unittest.TestCase):
    def test_pinned_remote_script_root_layout_is_healthy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            state = home / ".n0te-ableton-ai"
            user_library = root / "Ableton User Library"
            remote = user_library / "Remote Scripts" / "Ableton_Live_MCP"
            remote.mkdir(parents=True)
            state.mkdir(parents=True)

            (remote / "__init__.py").write_text("# remote script\n", encoding="utf-8")
            (remote / "bridge.py").write_text("# bridge\n", encoding="utf-8")
            (state / "install_manifest.json").write_text(
                json.dumps({"ableton_user_library": str(user_library)}),
                encoding="utf-8",
            )

            def probe(port):
                return port in (8765, 8766)

            with patch.object(n0te_doctor, "_probe", side_effect=probe):
                result = n0te_doctor.remote_script_doctor(state, home=home)

            self.assertEqual(
                result["required_files"],
                [str(remote / "__init__.py"), str(remote / "bridge.py")],
            )
            self.assertEqual(result["missing_required_files"], [])
            self.assertFalse(result["extra_nested_folder"])
            self.assertTrue(result["files_installed"])
            self.assertTrue(result["bridge"]["responding"])
            self.assertFalse(result["installed_but_not_loaded"])

    def test_duplicate_nested_remote_script_folder_is_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            state = home / ".n0te-ableton-ai"
            user_library = root / "Ableton User Library"
            remote = user_library / "Remote Scripts" / "Ableton_Live_MCP"
            nested = remote / "Ableton_Live_MCP"
            nested.mkdir(parents=True)
            state.mkdir(parents=True)

            (remote / "__init__.py").write_text("# remote script\n", encoding="utf-8")
            (remote / "bridge.py").write_text("# bridge\n", encoding="utf-8")
            (state / "install_manifest.json").write_text(
                json.dumps({"ableton_user_library": str(user_library)}),
                encoding="utf-8",
            )

            with patch.object(n0te_doctor, "_probe", return_value=False):
                result = n0te_doctor.remote_script_doctor(state, home=home)

            self.assertTrue(result["extra_nested_folder"])
            self.assertFalse(result["files_installed"])


if __name__ == "__main__":
    unittest.main()

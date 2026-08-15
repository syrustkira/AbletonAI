import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "INSTALL_N0TE_MAC.command"


class MacBootstrapTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(BOOTSTRAP)], check=True)

    def test_pinned_python_source_checksum_signer_and_cert_setup(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('PYTHON_VERSION="3.13.15"', text)
        self.assertIn("https://www.python.org/ftp/python/", text)
        self.assertIn(
            "3b7eaf7f29825f796e8267024435540ddf1f17fc9a97ad58095daa7a75bfdcd3",
            text,
        )
        self.assertIn("shasum -a 256", text)
        self.assertIn("pkgutil --check-signature", text)
        self.assertIn("Python Software Foundation", text)
        self.assertIn("BMM5U3QVKW", text)
        self.assertIn("Install Certificates.command", text)
        self.assertIn("sudo /usr/sbin/installer", text)
        self.assertIn("/usr/bin/python3", text)

    def test_existing_python_validation_path(self):
        with tempfile.TemporaryDirectory() as td_text:
            td = Path(td_text)
            fakebin = td / "bin"
            fakebin.mkdir()
            fake_python = fakebin / "python3"
            fake_python.write_text(
                '#!/bin/bash\nif [ "$1" = "--version" ]; then echo "Python 3.13.15"; exit 0; fi\nif [ "$1" = "-c" ]; then exit 0; fi\nexit 0\n',
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env["N0TE_BOOTSTRAP_ALLOW_NON_MAC"] = "1"
            env["N0TE_BOOTSTRAP_NO_GUI"] = "1"
            env["N0TE_BOOTSTRAP_VALIDATE_ONLY"] = "1"
            env["N0TE_BOOTSTRAP_SKIP_HTTPS_CHECK"] = "1"
            env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
            result = subprocess.run(
                ["bash", str(BOOTSTRAP)],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("Bootstrap validation OK", result.stdout)

    def _fake_prereq_bin(self, td: Path, signer: str) -> Path:
        fakebin = td / "bin"
        fakebin.mkdir()
        (fakebin / "curl").write_text(
            '#!/bin/bash\nout=""\nwhile [ $# -gt 0 ]; do if [ "$1" = "--output" ]; then shift; out="$1"; fi; shift || true; done\nprintf fake > "$out"\n',
            encoding="utf-8",
        )
        (fakebin / "shasum").write_text(
            '#!/bin/bash\necho "3b7eaf7f29825f796e8267024435540ddf1f17fc9a97ad58095daa7a75bfdcd3  $3"\n',
            encoding="utf-8",
        )
        (fakebin / "pkgutil").write_text(
            f'#!/bin/bash\necho "Status: signed"\necho "Developer ID Installer: {signer}"\n',
            encoding="utf-8",
        )
        (fakebin / "sudo").write_text('#!/bin/bash\nexit 99\n', encoding="utf-8")
        for p in fakebin.iterdir():
            p.chmod(0o755)
        return fakebin

    def test_missing_python_dry_run_accepts_expected_signer(self):
        with tempfile.TemporaryDirectory() as td_text:
            td = Path(td_text)
            fakebin = self._fake_prereq_bin(td, "Python Software Foundation (BMM5U3QVKW)")
            env = os.environ.copy()
            env.update({
                "N0TE_BOOTSTRAP_ALLOW_NON_MAC": "1",
                "N0TE_BOOTSTRAP_NO_GUI": "1",
                "N0TE_BOOTSTRAP_FORCE_MISSING_PYTHON": "1",
                "N0TE_BOOTSTRAP_DRY_RUN": "1",
                "PATH": str(fakebin) + os.pathsep + env.get("PATH", ""),
                "TMPDIR": str(td),
            })
            result = subprocess.run(
                ["bash", str(BOOTSTRAP)],
                cwd=ROOT,
                env=env,
                input="\n",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("signer validation succeeded", result.stdout)

    def test_missing_python_dry_run_rejects_wrong_signer(self):
        with tempfile.TemporaryDirectory() as td_text:
            td = Path(td_text)
            fakebin = self._fake_prereq_bin(td, "Unrelated Developer")
            env = os.environ.copy()
            env.update({
                "N0TE_BOOTSTRAP_ALLOW_NON_MAC": "1",
                "N0TE_BOOTSTRAP_NO_GUI": "1",
                "N0TE_BOOTSTRAP_FORCE_MISSING_PYTHON": "1",
                "N0TE_BOOTSTRAP_DRY_RUN": "1",
                "PATH": str(fakebin) + os.pathsep + env.get("PATH", ""),
                "TMPDIR": str(td),
            })
            result = subprocess.run(
                ["bash", str(BOOTSTRAP)],
                cwd=ROOT,
                env=env,
                input="\n",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("not by the expected Python Software Foundation", result.stdout)


if __name__ == "__main__":
    unittest.main()

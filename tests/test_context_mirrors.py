from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagedContextMirrorTests(unittest.TestCase):
    def test_packaged_context_mirrors_canonical_sources(self) -> None:
        """Packaged context is a mirror, never a second source of product truth."""
        text_mirrors = {
            ROOT / "BUILD_VALIDATION.md": ROOT / "app/context/BUILD_VALIDATION.md",
            ROOT / "HARDENING_AUDIT.md": ROOT / "app/context/HARDENING_AUDIT.md",
            ROOT / "INSTALLER_AUDIT.md": ROOT / "app/context/INSTALLER_AUDIT.md",
            ROOT / "PROJECT_BLUEPRINT.md": ROOT / "app/context/PROJECT_BLUEPRINT.md",
            ROOT / "README_FIRST.md": ROOT / "app/context/README_FIRST.md",
            ROOT / "THIRD_PARTY.md": ROOT / "app/context/THIRD_PARTY.md",
            ROOT / "docs/ROADMAP.md": ROOT / "app/context/ROADMAP.md",
            ROOT / "LICENSE": ROOT / "app/context/LICENSE-GPL-3.0.txt",
        }
        json_mirrors = {
            ROOT / "FEATURE_MATRIX.json": ROOT / "app/context/FEATURE_MATRIX.json",
            ROOT / "N0TE_CONTEXT_PACK.json": ROOT / "app/context/N0TE_CONTEXT_PACK.json",
        }

        for canonical, packaged in text_mirrors.items():
            with self.subTest(canonical=canonical.name, packaged=str(packaged.relative_to(ROOT))):
                self.assertEqual(
                    canonical.read_text(encoding="utf-8").splitlines(),
                    packaged.read_text(encoding="utf-8").splitlines(),
                    f"Packaged mirror drifted from canonical source: {packaged.relative_to(ROOT)}",
                )

        for canonical, packaged in json_mirrors.items():
            with self.subTest(canonical=canonical.name, packaged=str(packaged.relative_to(ROOT))):
                self.assertEqual(
                    json.loads(canonical.read_text(encoding="utf-8")),
                    json.loads(packaged.read_text(encoding="utf-8")),
                    f"Packaged JSON mirror drifted from canonical source: {packaged.relative_to(ROOT)}",
                )


if __name__ == "__main__":
    unittest.main()

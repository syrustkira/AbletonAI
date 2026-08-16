import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "app" / "static" / "index.html"


class UiSettingsTests(unittest.TestCase):
    def test_settings_open_rehydrates_saved_update_preferences(self):
        text = HTML.read_text(encoding="utf-8")
        self.assertIn('onclick="openSettings()"', text)
        self.assertIn("function openSettings(){hydrateSettings();settings.showModal()}", text)
        self.assertIn("$('updateChannel').value=c.update_channel||'STABLE'", text)
        self.assertIn("$('automaticUpdateChecking').value=String(Boolean(c.automatic_update_checking))", text)
        self.assertIn("$('automaticSafeInstall').value=String(Boolean(c.automatic_safe_install))", text)
        self.assertIn("hydrateSettings(d);", text)

    def test_update_controls_are_fail_closed_before_status_hydration(self):
        text = HTML.read_text(encoding="utf-8")
        checking = re.search(r'<select id="automaticUpdateChecking">(.*?)</select>', text)
        installing = re.search(r'<select id="automaticSafeInstall">(.*?)</select>', text)
        self.assertIsNotNone(checking)
        self.assertIsNotNone(installing)
        self.assertLess(checking.group(1).index('value="false"'), checking.group(1).index('value="true"'))
        self.assertLess(installing.group(1).index('value="false"'), installing.group(1).index('value="true"'))


if __name__ == "__main__":
    unittest.main()

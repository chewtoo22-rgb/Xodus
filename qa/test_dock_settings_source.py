#!/usr/bin/env python3
"""Check the actual prepared backend and preserved native Settings APIs."""
from pathlib import Path
import os
import unittest

REPO = Path(__file__).resolve().parents[1]


class DockSettingsSourceTests(unittest.TestCase):
    def test_native_page_uses_xodus_choices_and_keeps_existing_controls(self):
        page = (REPO / "overlay/identity/settings/qml/pages/AppearancePage.qml").read_text()
        self.assertNotIn("Tahoe", page)
        self.assertIn('Dock.set("skinName"', page)
        for mode in ("auto", "light", "dark"):
            self.assertIn('name: "' + mode + '"', page)
        for api in ("setAccent", "setAnimationSpeed", "setLgEnabled", "setTintEnabled"):
            self.assertIn("Appearance." + api, page)
        for api in ("Scrollbars.setAlwaysVisible", "Scrollbars.setClickToJump", "FilerConfig.setValue"):
            self.assertIn(api, page)

    @unittest.skipUnless(os.environ.get("XODUS_PREPARED_SETTINGS"), "requires the pinned prepared Settings source")
    def test_actual_prepared_backend_has_no_legacy_skin_or_icon_restore(self):
        source = Path(os.environ["XODUS_PREPARED_SETTINGS"])
        dock = (source / "backend/dockmanager.cpp").read_text()
        header = (source / "backend/dockmanager.h").read_text()
        for text in (dock, header):
            for old in ("Tahoe", "Big Sur"):
                self.assertNotIn(old, text)
            self.assertIn("Xodus Dark", text)
        self.assertIn('!m_availableSkins.contains(value.toString())', dock)
        appearance = (source / "backend/appearancemanager.cpp").read_text()
        function = appearance.split("void AppearanceManager::applyIconThemeForAccent", 1)[1].split("void AppearanceManager::maybeUpdateWallpaper", 1)[0]
        self.assertIn('dark ? "breeze-dark" : "breeze"', function)
        self.assertNotIn("pearOS", function)
        self.assertIn("accentColor.setAccentColor", appearance)
        self.assertIn("OnCalendar=*-*-* 08:00:00", appearance)
        self.assertEqual((source / "qml/pages/AppearancePage.qml").read_text(),
                         (REPO / "overlay/identity/settings/qml/pages/AppearancePage.qml").read_text())


if __name__ == "__main__":
    unittest.main()

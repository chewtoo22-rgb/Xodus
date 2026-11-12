#!/usr/bin/env python3
"""Exercise package-backed default selection and preflight rejection paths."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('desktop_identity', REPO / 'overlay/identity/desktop/apply-desktop-identity.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class DesktopIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / 'root'
        self.root.mkdir()
        for relative in desktop.DEPENDENCIES + ('usr/lib/qt6/plugins/org.kde.kdecoration3/org.kde.breeze.so',):
            self.write(relative, b'controlled dependency fixture')
        self.write('usr/share/color-schemes/Xodus.colors', (REPO / 'overlay/identity/shell/Xodus.colors').read_bytes())
        for home in ('etc/skel', 'home/liveuser'):
            for name in desktop.CONFIGS:
                self.write(home + '/.config/' + name, (REPO / 'qa/fixtures/desktop-identity' / name).read_bytes())
            self.write(home + '/.gtkrc-2.0', b'gtk-theme-name="Xodus-Light"\ngtk-cursor-theme-name="pearOS-cursors"\ngtk-icon-theme-name="pearOS-light"\n')
            for version in ('3', '4'):
                self.write(home + '/.config/gtk-' + version + '.0/settings.ini', b'[Settings]\ngtk-theme-name=Xodus-Dark\ngtk-cursor-theme-name=pearOS\ngtk-icon-theme-name=pearOS\ngtk-decoration-layout=close,minimize,maximize:\n')

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, contents):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    def test_real_reviewed_configurations_select_supported_controls_and_xodus_palette(self):
        original = (self.root / 'etc/skel/.config/kwinrc').read_text()
        desktop.apply(self.root)
        desktop.verify(self.root)
        window = (self.root / 'etc/skel/.config/kwinrc').read_text()
        self.assertIn('Library=org.kde.breeze\n', window)
        self.assertIn('ButtonsOnRight=IAX\n', window)
        self.assertEqual(window.split('[org.kde.kdecoration2]')[0], original.split('[org.kde.kdecoration2]')[0])
        colors = (self.root / 'etc/skel/.config/kdeglobals').read_text()
        self.assertIn('[Colors:Window]\nBackgroundAlternate=29,22,39\nBackgroundNormal=17,13,24\n', colors)
        self.assertIn('[Icons]\nTheme=breeze-dark\n', colors)
        self.assertIn('ScreenScaleFactors=Virtual-1=1;', colors)
        self.assertNotIn('WhiteSur', colors)
        self.assertIn('gtk-theme-name="Xodus-Light"', (self.root / 'etc/skel/.gtkrc-2.0').read_text())

    def test_missing_dependency_keeps_all_inputs(self):
        (self.root / desktop.DEPENDENCIES[0]).unlink()
        original = (self.root / 'etc/skel/.config/kdeglobals').read_bytes()
        with self.assertRaisesRegex(ValueError, 'dependency'):
            desktop.apply(self.root)
        self.assertEqual((self.root / 'etc/skel/.config/kdeglobals').read_bytes(), original)

    def test_second_home_drift_is_rejected_before_first_home_changes(self):
        (self.root / 'home/liveuser/.config/plasmarc').write_text('[Theme]\nname=unexpected\n')
        original = (self.root / 'etc/skel/.config/kdeglobals').read_bytes()
        with self.assertRaisesRegex(ValueError, 'input changed'):
            desktop.apply(self.root)
        self.assertEqual((self.root / 'etc/skel/.config/kdeglobals').read_bytes(), original)
        self.assertFalse((self.root / 'usr/lib/xodus/desktop-identity.json').exists())

    def test_symlinked_config_is_rejected(self):
        path = self.root / 'etc/skel/.config/kdeglobals'
        path.unlink()
        path.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            desktop.apply(self.root)

    def test_forging_receipt_cannot_admit_unreviewed_window_controls(self):
        import hashlib
        import json
        desktop.apply(self.root)
        path = self.root / 'etc/skel/.config/kwinrc'
        path.write_text(path.read_text().replace('Library=org.kde.breeze', 'Library=arbitrary'))
        receipt = self.root / 'usr/lib/xodus/desktop-identity.json'
        data = json.loads(receipt.read_text())
        data['files']['etc/skel/.config/kwinrc'] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'differ from source'):
            desktop.verify(self.root)


if __name__ == '__main__':
    unittest.main()

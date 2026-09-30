#!/usr/bin/env python3
"""Validate Settings staging refuses source/package/runtime drift."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / 'overlay/identity/settings/apply-settings.py'
spec = importlib.util.spec_from_file_location('settings_identity', HELPER)
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


class SettingsIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / 'root'
        self.root.mkdir()
        for relative in ('usr/bin/systemsettings1', 'usr/bin/system-overview'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'\x7fELFupstream fixture')
            path.chmod(0o755)
        self.launcher = self.root / 'usr/share/applications/pearos-systemsettings.desktop'
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text('[Desktop Entry]\nName=System Settings\n'
                                 'Comment=pearOS System Settings\nExec=systemsettings1\n'
                                 'Icon=systemsettings\nStartupWMClass=systemsettings1\n')
        self.original = self.launcher.read_bytes()
        self.binary = self.base / 'compiled'
        self.binary.write_bytes(b'\x7fELFXodus fixture')
        self.license = self.base / 'license.txt'
        self.license.write_text('GNU Public Licence V3 or newer\n')
        self.mode = 'pass'
        self.commands = []

    def tearDown(self):
        self.temporary.cleanup()

    def run_command(self, args, **kwargs):
        self.commands.append(args)
        if '/usr/bin/pacman' in args:
            package = args[-1]
            version = '26.7.0-1' if package == 'system-settings' else '26.3-1'
            if self.mode == 'version':
                version = '99.0-1'
            return subprocess.CompletedProcess(args, 0, package + ' ' + version + '\n', '')
        if '/usr/bin/ldd' in args:
            output = 'libQt6Core.so.6 libQt6Gui.so.6 libQt6Quick.so.6 libQt6Qml.so.6'
            if self.mode == 'library':
                output += '\nlibQt6Qml.so.6 => not found'
            return subprocess.CompletedProcess(args, 0, output, '')
        return subprocess.CompletedProcess(args, 70 if self.mode == 'render' else 0, '', '')

    def apply(self):
        with patch.object(identity.subprocess, 'run', side_effect=self.run_command):
            identity.apply(self.root, self.binary, self.license)

    def test_success_installs_native_app_compatibility_and_attribution(self):
        self.apply()
        executable = self.root / 'usr/lib/xodus/xodus-settings'
        self.assertEqual(executable.read_bytes(), self.binary.read_bytes())
        self.assertEqual(executable.stat().st_mode & 0o777, 0o755)
        self.assertIn('Xodus Settings', self.launcher.read_text())
        about = (self.root / 'usr/bin/system-overview').read_text()
        self.assertIn('/usr/lib/xodus/xodus-settings --about "$@"', about)
        self.assertIn('pearOS System Settings', (self.root / 'usr/share/licenses/xodus-settings/NOTICE').read_text())
        self.assertTrue(any('--about' in args and '--self-test' in args for args in self.commands))

    def test_wrong_package_version_is_rejected_before_writes(self):
        self.mode = 'version'
        with self.assertRaisesRegex(SystemExit, 'package version changed'):
            self.apply()
        self.assertEqual(self.launcher.read_bytes(), self.original)
        self.assertFalse((self.root / 'usr/lib/xodus/xodus-settings').exists())

    def test_missing_runtime_library_keeps_original_launchers(self):
        self.mode = 'library'
        with self.assertRaisesRegex(SystemExit, 'incompatible'):
            self.apply()
        self.assertEqual(self.launcher.read_bytes(), self.original)
        self.assertEqual((self.root / 'usr/bin/systemsettings1').read_bytes()[:4], b'\x7fELF')

    def test_failed_qml_render_keeps_original_entrypoints(self):
        self.mode = 'render'
        with self.assertRaisesRegex(SystemExit, 'cannot render'):
            self.apply()
        self.assertEqual((self.root / 'usr/bin/system-overview').read_bytes()[:4], b'\x7fELF')

    def test_changed_launcher_is_rejected_before_installing_binary(self):
        self.launcher.write_text(self.launcher.read_text().replace('Exec=systemsettings1', 'Exec=other-settings'))
        with self.assertRaisesRegex(SystemExit, 'desktop entry changed'):
            self.apply()
        self.assertFalse((self.root / 'usr/lib/xodus/xodus-settings').exists())

    def test_symlinked_entrypoint_is_rejected(self):
        path = self.root / 'usr/bin/systemsettings1'
        path.unlink()
        path.symlink_to(self.binary)
        with self.assertRaisesRegex(SystemExit, 'symlink'):
            self.apply()


if __name__ == '__main__':
    unittest.main()

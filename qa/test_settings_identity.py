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
        release = self.root / 'usr/lib/os-release'
        release.parent.mkdir(parents=True, exist_ok=True)
        release.write_text((REPO / 'overlay/identity/settings/upstream-os-release').read_text())
        (self.root / 'etc').mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_command(self, args, **kwargs):
        self.commands.append(args)
        if '/usr/bin/pacman' in args:
            package = args[-1]
            version = {'system-settings': '26.7.0-1', 'system-overview': '26.3-1', 'filesystem': '2026.09.18-1'}[package]
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
        self.assertEqual(identity.release_fields((self.root / 'usr/lib/os-release').read_text())['NAME'], 'Xodus')
        self.assertEqual((self.root / 'etc/os-release').readlink().as_posix(), '../usr/lib/os-release')

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

    def test_absolute_guest_release_symlink_never_follows_host_etc(self):
        (self.root / 'etc/os-release').symlink_to('/usr/lib/os-release')
        self.apply()
        self.assertEqual(identity.release_fields((self.root / 'usr/lib/os-release').read_text())['ID'], 'xodus')

    def test_release_path_escape_is_rejected_before_writes(self):
        (self.root / 'etc/os-release').symlink_to('../../outside')
        original = (self.root / 'usr/lib/os-release').read_bytes()
        with self.assertRaisesRegex(SystemExit, 'Unreviewed guest'):
            self.apply()
        self.assertEqual((self.root / 'usr/lib/os-release').read_bytes(), original)
        self.assertEqual(self.launcher.read_bytes(), self.original)

    def test_release_source_drift_is_rejected(self):
        release = self.root / 'usr/lib/os-release'
        release.write_text(release.read_text().replace('VERSION="26.9"', 'VERSION="99.1"'))
        with self.assertRaisesRegex(SystemExit, 'source changed'):
            self.apply()

    def test_real_builder_image_version_is_preserved(self):
        release = self.root / 'usr/lib/os-release'
        release.write_text(release.read_text().replace('IMAGE_ID=pearos-nicec0re', 'IMAGE_ID=Xodus-reference').replace('IMAGE_VERSION=26.9', 'IMAGE_VERSION=2026.10'))
        self.apply()
        fields = identity.release_fields(release.read_text())
        self.assertEqual(fields['IMAGE_VERSION'], '2026.10')
        self.assertEqual(fields['VERSION'], '26.9')
        self.assertEqual(fields['BUILD_ID'], 'rolling')

    def test_separate_release_files_must_agree_before_writes(self):
        release = self.root / 'etc/os-release'
        release.write_text((self.root / 'usr/lib/os-release').read_text().replace('IMAGE_VERSION=26.9', 'IMAGE_VERSION=2026.09'))
        original = (self.root / 'usr/lib/os-release').read_bytes()
        with self.assertRaisesRegex(SystemExit, 'files disagree'):
            self.apply()
        self.assertEqual((self.root / 'usr/lib/os-release').read_bytes(), original)
        self.assertFalse((self.root / 'usr/lib/xodus/upstream-os-release').exists())

    def test_unreviewed_builder_image_id_is_rejected_before_writes(self):
        release = self.root / 'usr/lib/os-release'
        release.write_text(release.read_text().replace('IMAGE_ID=pearos-nicec0re', 'IMAGE_ID=other-image'))
        original = release.read_bytes()
        with self.assertRaisesRegex(SystemExit, 'image provenance changed'):
            self.apply()
        self.assertEqual(release.read_bytes(), original)
        self.assertEqual(self.launcher.read_bytes(), self.original)

    def test_guest_release_link_loop_is_rejected(self):
        release = self.root / 'usr/lib/os-release'
        release.unlink()
        release.symlink_to('/etc/os-release')
        (self.root / 'etc/os-release').symlink_to('../usr/lib/os-release')
        with self.assertRaisesRegex(SystemExit, 'symlink loop'):
            self.apply()

    def test_invalid_builder_month_is_rejected(self):
        release = self.root / 'usr/lib/os-release'
        release.write_text(release.read_text().replace('IMAGE_VERSION=26.9', 'IMAGE_VERSION=2026.13'))
        with self.assertRaisesRegex(SystemExit, 'image provenance changed'):
            self.apply()


if __name__ == '__main__':
    unittest.main()

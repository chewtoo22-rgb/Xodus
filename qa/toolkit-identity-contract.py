#!/usr/bin/env python3
"""Disposable contracts using exact archived toolkit/theme-switcher packages."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / 'overlay/identity/toolkit'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = load('toolkit', SOURCE / 'apply-toolkit-identity.py')
U = load('toolkit_user_mode', SOURCE / 'apply-user-toolkit-mode.py')
LOCK = json.loads((SOURCE / 'source.lock.json').read_text())
PINS = None


def package_fixture(root):
    for archive, rows, expected in (
        (PINS.package, [p for p in LOCK['files'] if p not in M.SWITCHER['FILES']], LOCK['archive_sha256']),
        (PINS.switcher_package, list(M.SWITCHER['FILES']), LOCK['switcher']['archive_sha256']),
    ):
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise ValueError('archive pin changed: ' + str(archive))
        subprocess.run(['tar', '-xf', str(archive), '-C', str(root), *rows], check=True)
    shutil.copytree(root / 'etc/skel', root / 'home/liveuser')
    # Unrelated defaults and user records must survive, byte for byte.
    for home in M.HOMES:
        (root / home / '.config/konsolerc').write_text('[Desktop Entry]\nDefaultProfile=pearOS Normal.profile\n')
        (root / home / 'do-not-change').write_text('personal data\n')
    (root / 'etc/passwd').write_text('liveuser:x:1000:1000:Original User:/home/liveuser:/bin/zsh\n')


def run_apply(root, verify=False):
    def package_version(cmd, **kwargs):
        package = cmd[-1]
        version = LOCK['version'] if package == 'pearos-settings' else LOCK['switcher']['version']
        return subprocess.CompletedProcess(cmd, 0, package + ' ' + version + '\n', '')
    with contextlib.redirect_stdout(io.StringIO()), patch.object(M.subprocess, 'run', package_version):
        M.apply(root, verify)


class ToolkitContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xodus-toolkit-', dir='/var/tmp')
        self.root = Path(self.temp.name)
        package_fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_real_package_derivation_and_independent_verification(self):
        old = (self.root / 'etc/skel/.local/share/konsole/pearOS Normal.profile').read_bytes()
        run_apply(self.root)
        run_apply(self.root, True)
        profile = (self.root / 'etc/skel/.local/share/konsole/pearOS Normal.profile').read_text()
        self.assertIn('Command=/bin/zsh', profile)
        self.assertIn('Parent=FALLBACK/', profile)
        self.assertIn('Name=Xodus Terminal', profile)
        self.assertIn('Noto Sans Mono', profile)
        self.assertEqual((self.root / M.NOTICE_BASE / 'etc/skel/.local/share/konsole/pearOS Normal.profile').read_bytes(), old)
        self.assertIn('DefaultProfile=pearOS Normal.profile', (self.root / 'etc/skel/.config/konsolerc').read_text())
        self.assertEqual((self.root / 'etc/passwd').read_text(), 'liveuser:x:1000:1000:Original User:/home/liveuser:/bin/zsh\n')
        self.assertEqual((self.root / 'home/liveuser/do-not-change').read_text(), 'personal data\n')
        self.assertEqual(set(M.TRANSFER_FILES), set(M.SYSTEM_FILES) | set(M.NOTICE_FILES) | {'etc/skel/' + p for p in M.USER_CONFIGS})
        self.assertFalse(any(p.startswith('home/liveuser/') or p in ('etc/passwd', 'etc/hostname', 'etc/machine-id') for p in M.TRANSFER_FILES))

    def test_preserves_each_gtk_light_dark_preference(self):
        for home in M.HOMES:
            for suffix in M.PREFERENCES:
                path = self.root / home / suffix
                original = path.read_text()
                path.write_text(original.replace('pearOS-Dark', 'pearOS-Light').replace('prefer-dark-theme=true', 'prefer-dark-theme=false'))
        run_apply(self.root)
        run_apply(self.root, True)
        for home in M.HOMES:
            for suffix in M.PREFERENCES:
                self.assertIn('Xodus-Light', (self.root / home / suffix).read_text())
        # Package GTK2 starts Light while GTK3/4 start Dark; no forced unification.

    def test_input_drift_rejected_before_mutation(self):
        path = self.root / 'etc/skel/.local/share/konsole/pearOS Normal.profile'
        path.write_text(path.read_text().replace('/bin/zsh', '/bin/bash'))
        with self.assertRaisesRegex(ValueError, 'audited package input changed'):
            run_apply(self.root)
        self.assertFalse((self.root / M.RECEIPT).exists())
        self.assertIn('pearOS-Light', (self.root / 'etc/skel/.gtkrc-2.0').read_text())

    def test_unknown_preferences_rejected(self):
        path = self.root / 'etc/skel/.gtkrc-2.0'
        path.write_text(path.read_text().replace('pearOS-Light', 'CustomUnreviewed'))
        with self.assertRaisesRegex(ValueError, 'unreviewed toolkit preference'):
            run_apply(self.root)

    def test_receipt_rehash_does_not_authorize_css_change(self):
        run_apply(self.root)
        relative = 'usr/share/themes/Xodus-Dark/gtk-3.0/gtk.css'
        path = self.root / relative
        path.write_bytes(path.read_bytes() + b'button { opacity: 0; }\n')
        receipt_path = self.root / M.RECEIPT
        receipt = json.loads(receipt_path.read_text())
        receipt['outputs'][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
        with self.assertRaisesRegex(ValueError, 'retained toolkit bytes differ'):
            run_apply(self.root, True)

    def test_source_notice_mutation_rejected(self):
        run_apply(self.root)
        source = self.root / M.NOTICE_BASE / M.SWITCHER['FILES'][0]
        source.write_bytes(source.read_bytes() + b'# injected\n')
        with self.assertRaisesRegex(ValueError, 'audited package input changed'):
            run_apply(self.root, True)

    def test_symlink_and_new_output_rejected_before_mutation(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.root / 'usr/share/themes/Xodus-Dark').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            run_apply(self.root)
        self.assertFalse((self.root / M.RECEIPT).exists())
        (self.root / 'usr/share/themes/Xodus-Dark').unlink()
        target = self.root / M.RUNTIME
        target.parent.mkdir(parents=True)
        target.write_text('existing\n')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            run_apply(self.root)
        self.assertEqual(target.read_text(), 'existing\n')

    def test_closed_desktop_alternatives_and_modes(self):
        run_apply(self.root)
        for home in M.HOMES:
            for suffix in M.PREFERENCES:
                path = self.root / home / suffix
                text = path.read_text()
                quoted = suffix == '.gtkrc-2.0'
                for key, value in (('gtk-icon-theme-name', 'breeze-dark'), ('gtk-cursor-theme-name', 'breeze_cursors')):
                    text = M.key(text, key, '"' + value + '"' if quoted else value)
                if not quoted:
                    text = M.key(text, 'gtk-decoration-layout', ':minimize,maximize,close')
                path.write_text(text)
        run_apply(self.root, True)
        path = self.root / 'etc/skel/.config/gtk-3.0/settings.ini'
        path.write_text(M.key(path.read_text(), 'gtk-icon-theme-name', 'unreviewed-icon'))
        with self.assertRaisesRegex(ValueError, 'retained toolkit bytes differ'):
            run_apply(self.root, True)
        path.write_text(M.key(path.read_text(), 'gtk-icon-theme-name', 'breeze-dark'))
        (self.root / M.RUNTIME).chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'mode changed'):
            run_apply(self.root, True)

    def test_runtime_modes_preserve_modules_profile_ids_custom_choices(self):
        run_apply(self.root)
        home = self.root / 'home/liveuser'
        settings = home / '.config/gtk-3.0/settings.ini'
        original_module = M.key(settings.read_text(), 'gtk-modules')
        for mode in ('light', 'dark'):
            U.apply(home, mode)
            text = settings.read_text()
            self.assertEqual(M.key(text, 'gtk-modules'), original_module)
            self.assertEqual(M.key(text, 'gtk-theme-name'), 'Xodus-' + mode.title())
            self.assertEqual(M.key(text, 'gtk-font-name'), 'Noto Sans 10')
            self.assertIn('Command=/bin/zsh', (home / '.local/share/konsole/pearOS Normal.profile').read_text())
        profile = home / '.local/share/konsole/pearOS Normal.profile'
        profile.write_text(M.key(profile.read_text(), 'ColorScheme', 'My Custom Palette'))
        U.apply(home, 'light')
        self.assertIn('ColorScheme=My Custom Palette', profile.read_text())
        self.assertIn('DefaultProfile=pearOS Normal.profile', (home / '.config/konsolerc').read_text())

    def test_runtime_path_failure_does_not_partially_change_user_defaults(self):
        run_apply(self.root)
        home = self.root / 'home/liveuser'
        original = (home / '.gtkrc-2.0').read_bytes()
        directory = home / '.config/gtk-4.0'
        shutil.rmtree(directory)
        outside = self.root / 'outside-user-config'
        outside.mkdir()
        directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'unsafe user appearance path'):
            U.apply(home, 'light')
        self.assertEqual((home / '.gtkrc-2.0').read_bytes(), original)
        self.assertEqual(list(outside.iterdir()), [])

    def test_automatic_switcher_uses_xodus_paths_and_preserves_user_state(self):
        run_apply(self.root)
        source = self.root / M.SWITCHER['FILES'][0]
        subprocess.run(['bash', '-n', str(source)], check=True)
        home = self.root / 'home/liveuser'
        desktop = home / '.config/plasma-org.kde.plasma.desktop-appletsrc'
        desktop.write_text('Image=file:///home/liveuser/Pictures/default.jpg\n')
        tools = self.root / 'mockbin'
        tools.mkdir()
        log = self.root / 'commands.log'
        for command in ('kwriteconfig6', 'gsettings', 'qdbus6', 'plasma-apply-colorscheme', 'plasma-apply-desktoptheme', 'plasma-apply-cursortheme', 'plasma-apply-wallpaperimage'):
            path = tools / command
            path.write_text('#!/usr/bin/python3\nimport json,os,sys\nwith open(os.environ["COMMAND_LOG"],"a") as f: f.write(json.dumps([os.path.basename(sys.argv[0]),*sys.argv[1:]])+"\\n")\n')
            path.chmod(0o755)
        # Only substitute the runtime absolute path so this test cannot affect the host.
        runtime = self.root / M.RUNTIME
        source.write_text(source.read_text().replace('/usr/lib/xodus/apply-user-toolkit-mode', str(runtime)))
        adw = self.root / M.SWITCHER['BASE'] / 'libadwaita'
        adw.write_text(adw.read_text().replace('/usr/lib/xodus/apply-user-toolkit-mode', str(runtime)))
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'), COMMAND_LOG=str(log), PATH=str(tools) + ':/usr/bin:/bin')
        for mode in ('light', 'dark'):
            result = subprocess.run(['bash', str(source), '--' + mode], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(M.key((home / '.config/gtk-4.0/settings.ini').read_text(), 'gtk-theme-name'), 'Xodus-' + mode.title())
        commands = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertIn(['plasma-apply-colorscheme', 'Xodus Light'], commands)
        self.assertIn(['plasma-apply-colorscheme', 'Xodus'], commands)
        self.assertIn(['kwriteconfig6', '--file', 'kdeglobals', '--group', 'KDE', '--key', 'widgetStyle', 'Breeze'], commands)
        self.assertTrue(any('Xodus Light' in row[-1] and "'PearDock'" in row[-1] for row in commands if row[0] == 'qdbus6'))
        self.assertTrue(any('Xodus Dark' in row[-1] for row in commands if row[0] == 'qdbus6'))
        self.assertFalse(any(row[0] == 'plasma-apply-wallpaperimage' for row in commands))
        self.assertFalse(any(row[0] in ('nautilus', 'kvantumctl') for row in commands))
        self.assertIn('appmenu-gtk-module', (home / '.config/gtk-3.0/settings.ini').read_text())
        self.assertFalse((home / '.config/gtk-4.0/gtk.css').is_symlink())
        self.assertEqual(desktop.read_text(), 'Image=file:///home/liveuser/Pictures/default.jpg\n')
        result = subprocess.run(['bash', str(source), '--accent', 'purple'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertFalse(any('pearOS' in argument for row in commands for argument in row))
        preset = (self.root / M.SWITCHER['PRESETS'][-2]).read_text()
        self.assertNotIn('[KScreen]', preset)
        self.assertNotIn('ColorScheme=', preset)

    def test_palette_text_contrast(self):
        def luminance(color):
            values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
            return sum(v * factor for v, factor in zip(linear, (.2126, .7152, .0722)))
        for mode in ('Dark', 'Light'):
            p = M.palette(mode)
            for foreground, background in ((p['fg'], p['bg']), (p['fg'], p['base']), (p['selection_fg'], p['selected'])):
                a, b = sorted((luminance(foreground), luminance(background)))
                self.assertGreaterEqual((b + .05) / (a + .05), 4.5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--switcher-package', type=Path, required=True)
    PINS, extra = parser.parse_known_args()
    unittest.main(argv=[__file__, *extra])

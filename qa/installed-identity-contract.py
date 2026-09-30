#!/usr/bin/env python3
"""Disposable graphical transfer tests, using a fresh audited installer checkout.

Nothing executes setup/post_setup or performs a disk installation. Their shell
syntax and deterministic byte derivation are tested against pinned Git blobs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / 'overlay/identity/installed'
SOURCE = 'b' * 40
ORIGINAL_ROOT = None


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


payload = module('identity_payload', HERE / 'identity-payload.py')
derive = module('derive_installer', HERE / 'derive-installer-identity.py')
restore = module('restore_identity', HERE / 'restore-user-identity.py')


def write(root, relative, data, mode=0o644):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    path.chmod(mode)
    return path


def make_live(root):
    for relative in set(payload.FIXED) | payload.BOOT_REQUIRED:
        data = b'reviewed identity fixture\n'
        if relative in ('usr/lib/xodus/xodus-welcome', 'usr/lib/xodus/xodus-settings'):
            data = b'\x7fELFdisposable fixture; actual ABI is checked by the build gate\n'
        write(root, relative, data, int(payload.file_mode(relative), 8))
    markers = {
        'usr/share/applications/xodus-welcome.desktop': 'Name=Xodus Welcome\n',
        'usr/share/applications/pearos-systemsettings.desktop': 'Name=Xodus Settings\n',
        'etc/sddm.conf.d/20-xodus-theme.conf': '[Theme]\nCurrent=Xodus\n',
        'etc/skel/.config/kdeglobals': '[General]\nColorScheme=Xodus\n',
        'usr/share/color-schemes/Xodus.colors': '[General]\nName=Xodus\n',
        'usr/share/grub/themes/Xodus/theme.txt': 'text="Xodus"\n',
        'usr/share/plymouth/themes/xodus/xodus.plymouth': 'Name=Xodus\n',
        'usr/lib/os-release': 'NAME="Xodus"\nID=xodus\nVERSION="26.9"\n',
        'usr/lib/xodus/build-info': 'XODUS_SOURCE_COMMIT=' + SOURCE + '\nXODUS_INSTALLER_COMMIT=' + derive.INSTALLER_COMMIT + '\n',
    }
    for relative, data in markers.items():
        write(root, relative, data)
    payload.capture(root)


def make_target(root):
    (root / 'home/default').mkdir(parents=True)
    uid, gid = max(1000, os.getuid()), os.getgid()
    if os.geteuid() == 0:
        os.chown(root / 'home/default', uid, gid)
    write(root, 'etc/passwd', f'root:x:0:0:root:/root:/bin/bash\ndefault:x:{uid}:{gid}:Default User:/home/default:/bin/bash\n')
    write(root, 'etc/default/grub', 'GRUB_DISTRIBUTOR="Arch"\nGRUB_CMDLINE_LINUX_DEFAULT="loglevel=3"\n')
    write(root, 'etc/mkinitcpio.conf', 'HOOKS=(base udev autodetect microcode modconf kms keyboard block encrypt filesystems fsck)\n')
    write(root, 'etc/hostname', 'keep-target-hostname\n')
    write(root, 'etc/sudoers', 'keep-target-account-policy\n')
    write(root, 'usr/lib/xodus/build-info', 'keep-target-provenance\n')
    write(root, 'home/default/Documents/keep.txt', 'User content\n')


class PayloadContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='xodus-installed-identity-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.live, self.target = self.base / 'live', self.base / 'target'
        self.live.mkdir()
        self.target.mkdir()
        make_live(self.live)
        make_target(self.target)

    def install(self, phase='full'):
        with mock.patch.object(payload, 'runtime_check'):
            payload.install(self.live, self.target, SOURCE, phase)

    def test_boot_precedes_full_and_preserves_hooks(self):
        self.install('boot')
        self.assertFalse((self.target / 'usr/lib/xodus/xodus-settings').exists())
        for relative in payload.BOOT_REQUIRED:
            self.assertEqual((self.target / relative).read_bytes(), (self.live / relative).read_bytes())
        hooks = (self.target / 'etc/mkinitcpio.conf').read_text()
        self.assertIn('kms plymouth keyboard block encrypt filesystems fsck', hooks)
        self.assertIn('GRUB_THEME="/usr/share/grub/themes/Xodus/theme.txt"', (self.target / 'etc/default/grub').read_text())
        self.install()
        for relative in payload.FIXED:
            self.assertEqual((self.target / relative).read_bytes(), (self.live / relative).read_bytes())
        self.assertEqual(os.readlink(self.target / 'etc/os-release'), '../usr/lib/os-release')
        for relative in payload.SKEL:
            self.assertEqual((self.target / 'home/default' / relative).read_bytes(),
                             (self.live / 'etc/skel' / relative).read_bytes())
        self.assertEqual((self.target / 'etc/hostname').read_text(), 'keep-target-hostname\n')
        self.assertEqual((self.target / 'etc/sudoers').read_text(), 'keep-target-account-policy\n')
        self.assertEqual((self.target / 'usr/lib/xodus/build-info').read_text(), 'keep-target-provenance\n')
        self.assertEqual((self.target / 'home/default/Documents/keep.txt').read_text(), 'User content\n')
        self.assertEqual((self.target / 'usr/lib/xodus/xodus-settings').stat().st_mode & 0o777, 0o755)

    def test_real_installer_boundary_predicate_without_root_operations(self):
        payload.target_boundary(Path('/'), Path('/mnt'))
        for source, target in ((Path('/'), Path('/')), (Path('/'), Path('/home/user')),
                               (self.live, self.live), (self.live, self.live / 'target'),
                               (self.target / 'source', self.target)):
            with self.subTest(source=source, target=target):
                with self.assertRaises(ValueError):
                    payload.target_boundary(source, target)

    def test_sddm_conflicts_removed_while_account_settings_preserved(self):
        write(self.target, 'etc/sddm.conf', '[Autologin]\nUser=default\nSession=plasma.desktop\n\n[Theme]\nCurrent=pearOS\nCursorTheme=breeze\n')
        write(self.target, 'etc/sddm.conf.d/99-package.conf', '[General]\nInputMethod=qtvirtualkeyboard\n[Theme]\nCurrent=pearOS-dark\n')
        self.install()
        text = (self.target / 'etc/sddm.conf').read_text()
        self.assertIn('User=default\nSession=plasma.desktop', text)
        self.assertIn('CursorTheme=breeze', text)
        self.assertNotIn('Current=', text)
        self.assertNotIn('Current=', (self.target / 'etc/sddm.conf.d/99-package.conf').read_text())
        self.assertIn('InputMethod=qtvirtualkeyboard', (self.target / 'etc/sddm.conf.d/99-package.conf').read_text())
        self.assertEqual((self.target / 'etc/sddm.conf.d/20-xodus-theme.conf').read_text(), '[Theme]\nCurrent=Xodus\n')

    def test_unsafe_sddm_selection_rejected_before_any_transfer(self):
        file = write(self.base, 'outside-sddm', '[Theme]\nCurrent=pearOS\n')
        (self.target / 'etc/sddm.conf').symlink_to(file)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.install()
        self.assertFalse((self.target / 'usr/lib/xodus/xodus-settings').exists())
        self.assertEqual(file.read_text(), '[Theme]\nCurrent=pearOS\n')

    def test_changed_source_rejects_before_target_changes(self):
        write(self.live, 'usr/share/pixmaps/xodus-app-icon.png', 'altered')
        before = (self.target / 'etc/default/grub').read_bytes()
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            self.install('boot')
        self.assertEqual((self.target / 'etc/default/grub').read_bytes(), before)
        self.assertFalse((self.target / 'usr/share/grub/themes/Xodus/theme.txt').exists())

    def test_manifest_cannot_authorize_additional_code_or_wrong_mode(self):
        manifest_path = self.live / payload.MANIFEST
        original = json.loads(manifest_path.read_text())
        extra = copy.deepcopy(original)
        file = write(self.live, 'usr/share/plymouth/themes/xodus/run-command.py', '# arbitrary code\n')
        extra['files'].append({'path': file.relative_to(self.live).as_posix(), 'mode': '0755',
                               'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
        extra['files'].sort(key=lambda entry: entry['path'])
        manifest_path.write_text(json.dumps(extra))
        with self.assertRaisesRegex(ValueError, 'unreviewed path'):
            self.install('boot')
        wrong = copy.deepcopy(original)
        next(entry for entry in wrong['files'] if entry['path'] == 'usr/lib/xodus/xodus-settings')['mode'] = '0644'
        manifest_path.write_text(json.dumps(wrong))
        with self.assertRaisesRegex(ValueError, 'hash or mode'):
            self.install()

    def test_source_and_destination_symlinks_rejected(self):
        icon = self.live / 'usr/share/pixmaps/xodus-app-icon.png'
        data = icon.read_bytes()
        icon.unlink()
        outside = write(self.base, 'outside.png', data)
        icon.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.install('boot')
        icon.unlink()
        icon.write_bytes(data)
        (self.target / 'usr/share').mkdir(parents=True)
        (self.target / 'usr/share/plymouth').symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.install('boot')
        self.assertFalse((self.base / 'themes/xodus/xodus.script').exists())

    def test_hardlink_destination_cannot_overwrite_another_file(self):
        outside = write(self.base, 'unrelated-defaults', 'unchanged\n')
        destination = self.target / 'usr/share/grub/themes/Xodus/theme.txt'
        destination.parent.mkdir(parents=True)
        os.link(outside, destination)
        with self.assertRaisesRegex(ValueError, 'hardlink'):
            self.install('boot')
        self.assertEqual(outside.read_text(), 'unchanged\n')

    def test_unknown_source_and_release_link_fail_before_transfer(self):
        with self.assertRaisesRegex(ValueError, 'qualified installer'):
            payload.install(self.live, self.target, 'c' * 40)
        (self.target / 'etc/os-release').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'release symlink'):
            self.install()
        self.assertFalse((self.target / 'usr/lib/xodus/xodus-settings').exists())

    def test_actual_runtime_contract_checks_both_apps_and_aborts_missing_abi(self):
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            if '/usr/bin/ldd' in command:
                libs = 'libQt5Widgets.so.5 libQt5Gui.so.5 libQt5Core.so.5 libQt6Core.so.6 libQt6Gui.so.6 libQt6Quick.so.6 libQt6Qml.so.6'
                return subprocess.CompletedProcess(command, 0, libs, '')
            return subprocess.CompletedProcess(command, 0, 'render passed', '')
        with mock.patch.object(payload.subprocess, 'run', side_effect=run):
            payload.install(self.live, self.target, SOURCE)
        self.assertEqual(len(commands), 4)
        self.assertTrue(all(command[:2] == ['arch-chroot', str(self.target)] for command in commands))
        self.assertIn('--about', commands[-1])
        (self.target / 'usr/lib/xodus/installed-identity.json').unlink()
        with mock.patch.object(payload.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'libQt6Core.so.6 => not found', '')):
            with self.assertRaisesRegex(ValueError, 'ABI check failed'):
                payload.install(self.live, self.target, SOURCE)
        self.assertFalse((self.target / 'usr/lib/xodus/installed-identity.json').exists())

    def test_restore_only_reviewed_defaults_after_reset(self):
        self.install()
        globals_file = self.target / 'home/default/.config/kdeglobals'
        globals_file.write_text('ColorScheme=pearOS-dark\n')
        restore.restore(self.target, Path('/home/default'))
        self.assertEqual(globals_file.read_bytes(), (self.live / 'etc/skel/.config/kdeglobals').read_bytes())
        self.assertEqual((self.target / 'home/default/Documents/keep.txt').read_text(), 'User content\n')
        self.assertFalse((self.target / 'home/default/.config/autostart/pearos-first-theme.desktop').exists())

    def test_restore_tamper_and_home_symlink_fail_before_user_mutation(self):
        self.install()
        globals_file = self.target / 'home/default/.config/kdeglobals'
        globals_file.write_text('keep user configuration\n')
        write(self.target, 'etc/skel/.config/ksplashrc', 'tampered defaults\n')
        with self.assertRaisesRegex(ValueError, 'defaults changed'):
            restore.restore(self.target, Path('/home/default'))
        self.assertEqual(globals_file.read_text(), 'keep user configuration\n')
        (self.target / 'home/other').symlink_to(self.target / 'home/default')
        with self.assertRaisesRegex(ValueError, 'real directory'):
            restore.restore(self.target, Path('/home/other'))


class InstallerDerivationContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='xodus-installer-derivation-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.embedded = self.base / 'embedded'
        self.embedded.mkdir()
        self.original = derive.originals(ORIGINAL_ROOT)
        for path, data in self.original.items():
            write(self.embedded, path, data, 0o755)
        self.build_info = write(self.base, 'build-info', 'XODUS_SOURCE_COMMIT=' + SOURCE + '\nXODUS_INSTALLER_COMMIT=' + derive.INSTALLER_COMMIT + '\n')

    def process(self, verify=False):
        derive.process(self.embedded, ORIGINAL_ROOT, SOURCE, self.build_info, verify)

    def test_exact_derivation_order_syntax_and_safety_commands(self):
        self.process()
        self.process(True)
        setup = (self.embedded / 'system_install/setup').read_text()
        post = (self.embedded / 'post-install/post_setup').read_text()
        self.assertLess(setup.index('xodus-identity-payload verify'), setup.index('wipefs -a "$DISK"'))
        self.assertLess(setup.index('--phase boot'), setup.index('arch-chroot /mnt mkinitcpio'))
        self.assertGreater(setup.index('--phase full'), setup.rindex('rm -rf /mnt/usr/share/applications/'))
        self.assertLess(post.index('"$THEME_SWITCHER" --$THEME_MODE'), post.index('xodus-restore-user-identity'))
        # No executable disk or account command from the pinned originals may
        # change; only graphical selectors and the new read-only/copy hooks do.
        command_prefixes = ('wipefs ', 'parted ', 'sgdisk ', 'mkfs.', 'pacstrap ', 'useradd ',
                            'chpasswd ', 'usermod ', 'chwd ', 'grub-install ', 'loadkeys ')
        def protected(text):
            return [line for line in text.splitlines() if any(prefix in line for prefix in command_prefixes)]
        for relative, data in self.original.items():
            self.assertEqual(protected(data.decode()), protected((self.embedded / relative).read_text()))
            subprocess.run(['bash', '-n', str(self.embedded / relative)], check=True)
            self.assertNotIn(b'\r', (self.embedded / relative).read_bytes())

    def test_updated_self_hash_cannot_authorize_installer_mutation(self):
        self.process()
        for relative in derive.ORIGINAL_BLOBS:
            with self.subTest(script=relative):
                file = self.embedded / relative
                original = file.read_bytes()
                file.write_bytes(original + b'\n# unreviewed alteration\n')
                document = json.loads((self.embedded / derive.RECEIPT).read_text())
                document['derived'][relative]['sha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
                (self.embedded / derive.RECEIPT).write_text(json.dumps(document, indent=2) + '\n')
                with self.assertRaisesRegex(ValueError, 'deterministic derivation'):
                    self.process(True)
                file.write_bytes(original)
        (self.embedded / derive.RECEIPT).write_bytes(derive.receipt(self.original, derive.derive(self.original, SOURCE), SOURCE))
        self.process(True)

    def test_wrong_build_info_or_raw_script_fail_before_apply(self):
        self.build_info.write_text('XODUS_SOURCE_COMMIT=' + 'c' * 40 + '\nXODUS_INSTALLER_COMMIT=' + derive.INSTALLER_COMMIT + '\n')
        with self.assertRaisesRegex(ValueError, 'build-info'):
            self.process()
        self.assertFalse((self.embedded / derive.RECEIPT).exists())
        self.build_info.write_text('XODUS_SOURCE_COMMIT=' + SOURCE + '\nXODUS_INSTALLER_COMMIT=' + derive.INSTALLER_COMMIT + '\n')
        write(self.embedded, 'system_install/setup', self.original['system_install/setup'] + b'\n# changed frontend must not touch this\n')
        with self.assertRaisesRegex(ValueError, 'preserve protected'):
            self.process()
        self.assertFalse((self.embedded / derive.RECEIPT).exists())

    def test_cli_requires_exact_audited_objects(self):
        result = subprocess.run(['python3', str(HERE / 'derive-installer-identity.py'), '--apply-installer', str(self.embedded),
                                 '--original-root', str(ORIGINAL_ROOT), '--source-commit', SOURCE,
                                 '--build-info', str(self.build_info)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run(['python3', str(HERE / 'derive-installer-identity.py'), '--verify-installer', str(self.embedded),
                                 '--original-root', str(ORIGINAL_ROOT), '--source-commit', SOURCE,
                                 '--build-info', str(self.build_info)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # A copied directory with no audited Git database cannot be the authority.
        with self.assertRaises(subprocess.CalledProcessError):
            derive.process(self.embedded, self.embedded, SOURCE, self.build_info, True)

    def test_first_theme_entry_runs_once_even_on_restore_failure(self):
        self.process()
        post = (self.embedded / 'post-install/post_setup').read_text()
        anchor = '  cat > "$FIRST_THEME_SCRIPT" << EOF\n'
        body = post.split(anchor, 1)[1].split('\nEOF\n', 1)[0]
        stub = write(self.base, 'restore-stub', '#!/bin/sh\nexit "$RESTORE_EXIT"\n', 0o755)
        for code in (0, 70):
            with self.subTest(restore_exit=code):
                desktop = write(self.base, 'first-theme.desktop', 'one-time entry\n')
                script = self.base / 'first-theme.sh'
                environment = dict(os.environ, FIRST_THEME_SCRIPT=str(script), FIRST_THEME_DESKTOP=str(desktop),
                                   USER_HOME='/home/default', THEME_SWITCHER='/bin/true', THEME_MODE='dark',
                                   RESTORE_EXIT=str(code))
                # Execute only the extracted one-time heredoc with a disposable
                # stand-in for restoration. No installer/backend commands run.
                contents = anchor + body.replace('/usr/lib/xodus/xodus-restore-user-identity', str(stub)) + '\nEOF\n'
                subprocess.run(['bash', '-c', contents], env=environment, check=True)
                result = subprocess.run(['bash', str(script)], env=environment)
                self.assertEqual(result.returncode, code)
                self.assertFalse(desktop.exists())
                self.assertFalse(script.exists())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-root', type=Path, required=True)
    args = parser.parse_args()
    ORIGINAL_ROOT = args.original_root.resolve(strict=True)
    unittest.main(argv=[__file__], verbosity=2)

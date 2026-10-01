"""Exercise produced-image graphics extraction with a real squashfs archive.

Only privileged ISO/FAT/initramfs operations are simulated. The actual build
helper, selective unsquashfs extraction and retained graphical checker run.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from graphical_payload_fixture import make_graphical_fixture


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / 'qa/verify-built-boot.sh'


@unittest.skipUnless(os.name == 'posix' and shutil.which('mksquashfs') and shutil.which('unsquashfs'),
                     'requires Linux squashfs-tools')
class ProducedGraphicalPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='xodus-produced-graphics-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.build = self.base / 'build'
        self.live = self.base / 'live'
        self.reference = self.build / 'pear/xodus-graphical-contract'
        make_graphical_fixture(self.reference, self.live)
        self.iso_tree = self.base / 'iso-tree'
        self.squashfs = self.iso_tree / 'arch/x86_64/airootfs.sfs'
        self.squashfs.parent.mkdir(parents=True)
        initramfs = self.iso_tree / 'arch/boot/x86_64/initramfs-linux.img'
        initramfs.parent.mkdir(parents=True)
        initramfs.write_bytes(b'disposable initramfs marker')
        (self.iso_tree / 'iso-proof.txt').write_text('ISO tree was mounted')
        (self.build / 'Xodus-reference-fixture.iso').write_bytes(b'disposable ISO mount marker')
        self.efi = self.build / 'work/tmp.fixture/efiboot.img'
        self.efi.parent.mkdir(parents=True)
        self.efi.write_bytes(b'disposable FAT marker')
        self.report = self.build / 'xodus-graphical-payload-verification.json'
        self.commands = self.base / 'commands'
        self.commands.mkdir()
        self.log = self.base / 'boot-checks.txt'
        self.environment = dict(os.environ, PATH=str(self.commands) + os.pathsep + os.environ['PATH'],
                                XODUS_TEST_ISO_TREE=str(self.iso_tree), XODUS_TEST_BOOT_LOG=str(self.log))
        self.write_command('mount', '''import os, shutil, sys
shutil.copytree(os.environ['XODUS_TEST_ISO_TREE'], sys.argv[-1], dirs_exist_ok=True, symlinks=True)
''')
        self.write_command('mountpoint', 'raise SystemExit(1)\n')
        self.write_command('mcopy', '''from pathlib import Path
import sys
target = Path(sys.argv[-1]) / 'EFI/BOOT'
target.mkdir(parents=True)
(target / 'efi-proof.txt').write_text('Firmware image was extracted')
''')
        self.write_command('lsinitcpio', '''from pathlib import Path
Path('initramfs-proof.txt').write_text('Initramfs was extracted')
''')
        verifier = self.build / 'pear/xodus-boot-contract/verify-boot-identity.py'
        verifier.parent.mkdir(parents=True)
        verifier.write_text('''import argparse, os
from pathlib import Path
p = argparse.ArgumentParser()
for name in ('iso', 'efi', 'initramfs', 'live'):
    p.add_argument('--' + name + '-root', type=Path)
a = p.parse_args()
checks = []
for name, marker in (('iso', 'iso-proof.txt'), ('efi', 'EFI/BOOT/efi-proof.txt'),
                     ('initramfs', 'initramfs-proof.txt'), ('live', 'etc/arch-release')):
    root = getattr(a, name + '_root')
    if root is not None:
        assert (root / marker).is_file(), 'required boot check input missing: ' + name
        if name == 'live':
            assert not (root / 'unrelated-large-payload.bin').exists(), 'extraction was not selective'
        checks.append(name)
with open(os.environ['XODUS_TEST_BOOT_LOG'], 'a') as log:
    log.write('\\n'.join(checks) + '\\n')
if os.environ.get('XODUS_TEST_BOOT_FAIL') in checks:
    raise SystemExit('boot verification rejected its payload')
''', encoding='utf-8')
        boot_marker = self.live / 'etc/arch-release'
        boot_marker.write_text('Xodus\n', encoding='utf-8')
        (self.live / 'unrelated-large-payload.bin').write_bytes(b'exclude from extraction')

    def write_command(self, name, source):
        path = self.commands / name
        path.write_text('#!/usr/bin/env python3\n' + source, encoding='utf-8')
        path.chmod(0o755)

    def build_archive(self):
        if self.squashfs.exists():
            self.squashfs.unlink()
        subprocess.run(['mksquashfs', str(self.live), str(self.squashfs), '-noappend',
                        '-no-progress', '-processors', '1'], check=True, capture_output=True)

    def run_helper(self):
        self.build_archive()
        return subprocess.run(['bash', str(SCRIPT), str(self.build), str(self.efi)],
                              env=self.environment, capture_output=True, text=True)

    def test_actual_archive_graphics_pass_with_every_boot_check(self):
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(self.report.read_text())
        self.assertEqual(document['graphical_identity'], 'pass')
        self.assertIn('usr/lib/xodus/xodus-settings', document['files'])
        self.assertEqual(self.log.read_text().splitlines(), ['iso', 'efi', 'initramfs', 'live'])
        self.assertFalse(list(self.build.glob('xodus-boot-audit.*')))

    def test_missing_graphics_in_actual_archive_fail_closed(self):
        (self.live / 'usr/share/wallpapers/Xodus/xodus-wallpaper.png').unlink()
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing graphical payload', result.stderr)
        self.assertFalse(self.report.exists())

    def test_altered_qml_in_actual_archive_is_rejected(self):
        path = self.live / 'usr/share/sddm/themes/Xodus/Main.qml'
        path.write_bytes(path.read_bytes() + b'changed after source staging')
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Graphical bytes differ', result.stderr)
        self.assertFalse(self.report.exists())

    def test_competing_theme_is_extracted_and_rejected(self):
        (self.live / 'etc/sddm.conf.d/99-unreviewed.conf').write_text('[Theme]\nCurrent=pearOS\n')
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Competing SDDM', result.stderr)
        self.assertFalse(self.report.exists())

    def test_boot_failure_still_aborts_before_graphical_report(self):
        self.environment['XODUS_TEST_BOOT_FAIL'] = 'initramfs'
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('boot verification rejected', result.stderr)
        self.assertFalse(self.report.exists())

    def test_missing_checker_removes_stale_report_and_aborts(self):
        self.report.write_text('{"stale":true}\n')
        (self.reference / 'qa/verify-graphical-identity.py').unlink()
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.report.exists())
        self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()

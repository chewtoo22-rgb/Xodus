#!/usr/bin/env python3
"""Install the source-built Settings app and check the staged live-root ABI."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def apply(root, binary, license_file):
    overlay = Path(__file__).resolve().parent
    lock = json.loads((overlay / "source.lock.json").read_text())
    root = root.resolve(strict=True)
    if root == Path("/"):
        raise SystemExit("Refusing the host root")
    def checked(relative):
        path = root / relative
        if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
            raise SystemExit("Settings path contains a symlink: " + relative)
        return path
    # Both compatibility entrypoints belong to audited installed packages.
    for package, version in ((lock['settings_package'], lock['settings_version']),
                             (lock['overview_package'], lock['overview_version'])):
        result = subprocess.run(['arch-chroot', str(root), '/usr/bin/pacman', '-Q', package],
                                capture_output=True, text=True, timeout=30)
        if result.returncode or result.stdout.strip() != package + ' ' + version:
            raise SystemExit('Settings package version changed: ' + package)
    for relative in ('usr/bin/systemsettings1', 'usr/bin/system-overview'):
        path = checked(relative)
        if not path.is_file() or path.read_bytes()[:4] != b'\x7fELF' or not os.access(path, os.X_OK):
            raise SystemExit('Settings package entrypoint changed: ' + relative)
    launcher = checked('usr/share/applications/pearos-systemsettings.desktop')
    original = launcher.read_text()
    for expected in ('Name=System Settings', 'Comment=pearOS System Settings', 'Exec=systemsettings1',
                     'Icon=systemsettings', 'StartupWMClass=systemsettings1'):
        if original.splitlines().count(expected) != 1:
            raise SystemExit('Settings package desktop entry changed: ' + expected)
    for name in ('Name', 'Comment', 'Exec', 'Icon'):
        if any(line.startswith(name + '[') for line in original.splitlines()):
            raise SystemExit('Unreviewed localized Settings launcher: ' + name)
    executable = checked('usr/lib/xodus/xodus-settings')
    if executable.exists():
        raise SystemExit('Xodus Settings is already staged')
    if binary.is_symlink() or not binary.is_file() or binary.read_bytes()[:4] != b'\x7fELF':
        raise SystemExit('Compiled Xodus Settings is not an ELF file')
    if license_file.is_symlink() or not license_file.is_file():
        raise SystemExit('Settings source license is missing')
    executable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(binary, executable)
    executable.chmod(0o755)
    result = subprocess.run(['arch-chroot', str(root), '/usr/bin/ldd', '/usr/lib/xodus/xodus-settings'],
                            capture_output=True, text=True, timeout=30)
    libraries = result.stdout + result.stderr
    required = ('libQt6Core.so.6', 'libQt6Gui.so.6', 'libQt6Quick.so.6', 'libQt6Qml.so.6')
    if result.returncode or 'not found' in libraries or any(name not in libraries for name in required):
        raise SystemExit('Xodus Settings is incompatible with live-root Qt:\n' + libraries)
    result = subprocess.run(['arch-chroot', str(root), '/usr/bin/env', 'LD_BIND_NOW=1',
                             'QT_QPA_PLATFORM=offscreen', 'QT_QUICK_BACKEND=software',
                             'QT_QUICK_CONTROLS_STYLE=Basic', '/usr/lib/xodus/xodus-settings',
                             '--self-test', '--about'], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise SystemExit('Xodus Settings cannot render in the live root:\n' + result.stdout + result.stderr)
    for relative, arguments in (('usr/bin/systemsettings1', ''), ('usr/bin/system-overview', '--about ')):
        path = checked(relative)
        path.write_text('#!/bin/sh\nexec /usr/lib/xodus/xodus-settings ' + arguments + '"$@"\n', newline='\n')
        path.chmod(0o755)
    # Reuse the existing launcher ID so dock pins keep working. App identity and
    # startup class refer to the rebuilt application instead of the package ID.
    launcher.write_text('[Desktop Entry]\nType=Application\nName=Xodus Settings\n'
                        'Comment=Configure your Xodus desktop and devices\nExec=systemsettings1\n'
                        'Icon=/usr/share/pixmaps/xodus-app-icon.png\nStartupWMClass=xodus-settings\n'
                        'Categories=Settings;System;\nTerminal=false\n', newline='\n')
    notices = checked('usr/share/licenses/xodus-settings')
    notices.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(license_file, notices / 'upstream-license.txt')
    (notices / 'NOTICE').write_text(
        'Xodus Settings includes GPL-3.0-or-later code from pearOS System Settings.\n'
        'Upstream author and maintainer: Alexandru Balan, Pear Software.\n'
        'Source: ' + lock['repository'] + '\nCommit: ' + lock['commit'] + '\n'
        'Xodus modifies the window, navigation, General and About screens and application identity.\n'
        'Existing upstream package license records are retained.\n', newline='\n')
    provenance = checked('usr/lib/xodus/settings-source.json')
    provenance.write_text(json.dumps(lock, indent=2) + '\n', newline='\n')
    print('Installed source-built Xodus Settings and About')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('binary', type=Path)
    parser.add_argument('license_file', type=Path)
    args = parser.parse_args()
    if args.root.is_symlink() or not args.root.is_dir():
        raise SystemExit('Settings live root must be a real directory')
    apply(args.root, args.binary, args.license_file)

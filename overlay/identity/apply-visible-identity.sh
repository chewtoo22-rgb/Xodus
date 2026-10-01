#!/usr/bin/env bash
set -euo pipefail

live_root=${1:-}
[[ -n "$live_root" && -d "$live_root" && "$live_root" != / ]] || {
  echo 'usage: apply-visible-identity.sh <live-root>' >&2
  exit 64
}

# Packages and customize_airootfs.sh create these files after the source
# profile is copied. Validate every expected upstream shape before writing.
python3 - "$live_root" <<'PY'
from pathlib import Path
import stat
import subprocess
import sys

root = Path(sys.argv[1]).resolve(strict=True)
if root == Path('/'):
    raise SystemExit('refusing to edit the filesystem root')


def checked_file(relative: str) -> Path:
    path = root / relative
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        raise SystemExit(f'expected regular live-root file is missing or unsafe: {relative}')
    return path


wallpaper = checked_file('usr/share/wallpapers/Xodus/xodus-wallpaper.png')
app_icon = checked_file('usr/share/pixmaps/xodus-app-icon.png')
for asset in (wallpaper, app_icon):
    with asset.open('rb') as handle:
        if handle.read(8) != b'\x89PNG\r\n\x1a\n':
            raise SystemExit(f'Xodus artwork is not a PNG: {asset.relative_to(root)}')

welcome = checked_file('usr/lib/xodus/xodus-welcome')
if welcome.open('rb').read(4) != b'\x7fELF':
    raise SystemExit('Xodus Welcome is not an ELF executable')
if not stat.S_IMODE(welcome.stat().st_mode) & 0o111:
    raise SystemExit('Xodus Welcome is not executable')
checked_file('usr/bin/pearos-welcome')

old_image = 'Image=file:///usr/share/extras/wallpapers/Default/dark-mode.jpg'
new_image = 'Image=file:///usr/share/wallpapers/Xodus/xodus-wallpaper.png'
desktop_old = {
    'Name': 'Install pearOS NiceC0re',
    'GenericName': 'pearOS Installer',
    'Comment': 'pearOS installer',
    'Icon': 'nicec0re-logo',
}
desktop_new = {
    'Name': 'Install Xodus',
    'GenericName': 'Xodus Installer',
    'Comment': 'Install Xodus to this computer',
    'Icon': '/usr/share/pixmaps/xodus-app-icon.png',
}
updates = {}


def old_welcome(relative: str, required: bool = True) -> Path | None:
    path = root / relative
    if not path.exists() and not path.is_symlink():
        if required:
            raise SystemExit(f'upstream Welcome entry is missing: {relative}')
        return None
    path = checked_file(relative)
    lines = path.read_text(encoding='utf-8').splitlines()
    for expected in ('[Desktop Entry]', 'Type=Application', 'Name=Welcome',
                     'Exec=pearos-welcome', 'Icon=/usr/share/pixmaps/welcome.png',
                     'Comment=pearOS - Welcome App'):
        if lines.count(expected) != 1:
            raise SystemExit(f'upstream Welcome entry changed: {relative}: {expected}')
    if any(line.startswith(('Name[', 'GenericName[', 'Comment[',
                            'Exec[', 'TryExec=')) for line in lines):
        raise SystemExit(f'unreviewed upstream Welcome override: {relative}')
    return path


menu = old_welcome('usr/share/applications/welcome.desktop')
skel_autostart = old_welcome('etc/skel/.config/autostart/welcome.desktop')
live_autostart = old_welcome('home/liveuser/.config/autostart/welcome.desktop', False)
for directory in ('usr/share/applications', 'etc/skel/.config/autostart',
                  'home/liveuser/.config/autostart'):
    for entry in (root / directory).glob('*.desktop'):
        if entry in (menu, skel_autostart, live_autostart):
            continue
        if entry.is_symlink() or not entry.is_file():
            continue
        if 'pearos-welcome' in entry.read_text(encoding='utf-8'):
            raise SystemExit(f'unreviewed upstream Welcome launcher: {entry.relative_to(root)}')

mask = '[Desktop Entry]\nHidden=true\n'
for path in (menu, skel_autostart):
    updates[path] = mask
live_autostart = root / 'home/liveuser/.config/autostart/welcome.desktop'
updates[live_autostart] = mask
menu_entry = '''[Desktop Entry]
Type=Application
Name=Xodus Welcome
GenericName=Welcome to Xodus
Comment=Start exploring the Xodus desktop
Exec=/usr/lib/xodus/xodus-welcome
Icon=/usr/share/pixmaps/xodus-app-icon.png
Terminal=false
Categories=System;
StartupNotify=true
'''
autostart_entry = menu_entry + 'OnlyShowIn=KDE;\nX-KDE-autostart-phase=2\n'
updates[root / 'usr/share/applications/xodus-welcome.desktop'] = menu_entry
updates[root / 'etc/skel/.config/autostart/xodus-welcome.desktop'] = autostart_entry
updates[root / 'home/liveuser/.config/autostart/xodus-welcome.desktop'] = autostart_entry

for relative in ('usr/share/applications/xodus-welcome.desktop',
                 'etc/skel/.config/autostart/xodus-welcome.desktop',
                 'home/liveuser/.config/autostart/xodus-welcome.desktop'):
    path = root / relative
    if path.exists() or path.is_symlink():
        raise SystemExit(f'Xodus Welcome entry already exists in upstream root: {relative}')


def split_line(line: str) -> tuple[str, str]:
    content = line.rstrip('\r\n')
    return content, line[len(content):]


for home in ('etc/skel', 'home/liveuser'):
    config = f'{home}/.config/plasma-org.kde.plasma.desktop-appletsrc'
    for relative in (config, f'{config}.bak'):
        path = checked_file(relative)
        original = path.read_bytes().decode('utf-8')
        lines = original.splitlines(keepends=True)
        if sum(split_line(line)[0] == old_image for line in lines) != 2:
            raise SystemExit(f'unexpected Plasma wallpaper layout: {relative}')
        if any(split_line(line)[0] == new_image for line in lines):
            raise SystemExit(f'Xodus wallpaper already present in upstream config: {relative}')
        updated = ''.join(
            new_image + split_line(line)[1]
            if split_line(line)[0] == old_image else line
            for line in lines
        )
        updates[path] = updated

    relative = f'{home}/Desktop/system_install.desktop'
    path = checked_file(relative)
    original = path.read_bytes().decode('utf-8')
    lines = original.splitlines(keepends=True)
    content_lines = [split_line(line)[0] for line in lines]
    if content_lines.count('[Desktop Entry]') != 1 or content_lines.count('Exec=bash bin_install') != 1:
        raise SystemExit(f'unexpected installer desktop entry: {relative}')
    for key, old_value in desktop_old.items():
        if content_lines.count(f'{key}={old_value}') != 1:
            raise SystemExit(f'unexpected installer {key} field: {relative}')
        if sum(line.startswith(f'{key}=') for line in content_lines) != 1:
            raise SystemExit(f'duplicate installer {key} field: {relative}')
    # An upstream localized field would override the base label in that locale.
    if any(line.startswith((f'{key}[',)) for line in content_lines
           for key in ('Name', 'GenericName', 'Comment')):
        raise SystemExit(f'unreviewed localized installer label: {relative}')
    updated_lines = []
    for line in lines:
        content, newline = split_line(line)
        for key, old_value in desktop_old.items():
            if content == f'{key}={old_value}':
                line = f'{key}={desktop_new[key]}' + newline
                break
        updated_lines.append(line)
    updates[path] = ''.join(updated_lines)

# Check the binary against the live root's actual Qt libraries and render the
# window offscreen. Nothing in the root is changed until every check passes.
ldd = subprocess.run(
    ['arch-chroot', str(root), '/usr/bin/ldd', '/usr/lib/xodus/xodus-welcome'],
    capture_output=True, text=True, timeout=30, check=False,
)
ldd_output = ldd.stdout + ldd.stderr
required_libraries = ('libQt5Widgets.so.5', 'libQt5Gui.so.5', 'libQt5Core.so.5')
if ldd.returncode or 'not found' in ldd_output or any(
    library not in ldd_output for library in required_libraries
):
    raise SystemExit(f'Xodus Welcome is incompatible with the live root:\n{ldd_output}')
self_test = subprocess.run(
    ['arch-chroot', str(root), '/usr/bin/env', 'LD_BIND_NOW=1',
     'QT_QPA_PLATFORM=offscreen', 'QT_STYLE_OVERRIDE=Fusion',
     '/usr/lib/xodus/xodus-welcome', '--self-test'],
    capture_output=True, text=True, timeout=30, check=False,
)
if self_test.returncode:
    raise SystemExit('Xodus Welcome cannot start in the live root:\n'
                     + self_test.stdout + self_test.stderr)

for path, updated in updates.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(updated.encode('utf-8'))

print('Applied Xodus wallpaper, installer launcher, and native Welcome identity')
PY

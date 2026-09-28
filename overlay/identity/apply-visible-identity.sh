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

for path, updated in updates.items():
    path.write_bytes(updated.encode('utf-8'))

print('Applied Xodus visible identity to live Plasma configs and installer launchers')
PY

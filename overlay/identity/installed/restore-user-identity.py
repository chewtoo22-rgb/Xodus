#!/usr/bin/env python3
"""Restore Xodus defaults once, after the audited first-login theme switch.

This helper creates no autostart entry. The derived post_setup heredoc invokes
it once and removes that upstream first-theme entry, including after failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

SKEL = (
    '.config/kscreenlockerrc', '.config/kdeglobals', '.config/ksplashrc',
    '.config/plasma-org.kde.plasma.desktop-appletsrc',
    '.config/plasma-org.kde.plasma.desktop-appletsrc.bak',
    '.config/filer-topbar-appletsrc', '.config/autostart/pearos-notch.desktop',
    '.config/autostart/welcome.desktop', '.config/autostart/xodus-welcome.desktop',
)


def fail(message):
    raise ValueError('Xodus first-login identity: ' + message)


def checked(root, relative, required=False):
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            fail('symlink in reviewed identity path: ' + relative)
        if candidate != path and candidate.exists() and not candidate.is_dir():
            fail('non-directory identity parent: ' + relative)
    if root not in path.resolve().parents or (path.exists() and not path.is_file()):
        fail('unsafe identity path: ' + relative)
    if path.is_file() and path.stat().st_nlink != 1:
        fail('hardlink in identity path: ' + relative)
    if required and not path.is_file():
        fail('reviewed identity file is missing: ' + relative)
    return path


def restore(root, home):
    if root.is_symlink() or not root.is_dir():
        fail('root must be a real directory')
    root = root.resolve(strict=True)
    if not home.is_absolute() or len(home.parts) != 3 or home.parts[1] != 'home' or home.parts[2] in ('.', '..'):
        fail('home must be one direct /home/user directory')
    relative_home = home.as_posix().lstrip('/')
    target = root / relative_home
    for candidate in (target, target.parent):
        if candidate.is_symlink() or not candidate.is_dir():
            fail('user home must be a real directory')
    if root not in target.resolve().parents:
        fail('user home escapes staged root')
    owner = target.stat()
    if root == Path('/') and (os.geteuid() == 0 or owner.st_uid != os.geteuid()):
        fail('first-login identity must run as the owner of the real user home')
    receipt = json.loads(checked(root, 'usr/lib/xodus/installed-identity.json', True).read_text())
    if (not isinstance(receipt, dict) or receipt.get('schema') != 1
            or not isinstance(receipt.get('files'), list)):
        fail('installed identity receipt is invalid')
    entries = {}
    for entry in receipt['files']:
        if not isinstance(entry, dict) or set(entry) != {'path', 'sha256', 'mode'}:
            fail('installed identity entry is invalid')
        path = entry['path']
        if not isinstance(path, str) or path in entries:
            fail('installed identity contains duplicate or invalid paths')
        entries[path] = entry
    updates = []
    for relative in SKEL:
        source = checked(root, 'etc/skel/' + relative, True)
        data = source.read_bytes()
        entry = entries.get('etc/skel/' + relative)
        if (entry is None or entry['mode'] != '0644'
                or hashlib.sha256(data).hexdigest() != entry['sha256']):
            fail('reviewed first-login defaults changed: ' + relative)
        destination = checked(root, relative_home + '/' + relative)
        if destination.exists() and destination.stat().st_uid != owner.st_uid:
            fail('user identity file belongs to another account: ' + relative)
        updates.append((destination, data))
    # Check the whole receipt and destination set before touching a user's files.
    for destination, data in updates:
        missing = []
        parent = destination.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        destination.parent.mkdir(parents=True, exist_ok=True)
        if os.geteuid() == 0:
            for parent in missing:
                os.chown(parent, owner.st_uid, owner.st_gid)
        destination.write_bytes(data)
        destination.chmod(0o644)
        if os.geteuid() == 0:
            os.chown(destination, owner.st_uid, owner.st_gid)
    if root == Path('/'):
        result = subprocess.run(['/usr/bin/plasma-apply-colorscheme', 'Xodus'],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            fail('Plasma did not accept the reviewed Xodus color scheme')
        result = subprocess.run(['/usr/bin/plasma-apply-wallpaperimage',
                                 '/usr/share/wallpapers/Xodus/xodus-wallpaper.png'],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            fail('Plasma did not accept the reviewed Xodus wallpaper')
    print('Restored reviewed Xodus graphical defaults for the first login')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/'))
    parser.add_argument('--home', type=Path, default=Path(os.environ.get('HOME', '')))
    args = parser.parse_args()
    try:
        restore(args.root, args.home)
    except (ValueError, OSError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc))

#!/usr/bin/env python3
"""Update only appearance keys when Xodus switches light/dark mode."""
from pathlib import Path
import argparse
import os
import re


def update(home, relative, values, section=None, required=False, pending=None):
    path = home / relative
    for parent in (path, *path.parents):
        if parent == home:
            break
        if parent.is_symlink() or (parent != path and parent.exists() and not parent.is_dir()):
            raise ValueError('unsafe user appearance path: ' + relative)
    if not path.exists() and not required:
        return
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('unsafe user appearance file: ' + relative)
    text = path.read_text() if path.exists() else ''
    if section and '[' + section + ']' not in text:
        text += '\n[' + section + ']\n'
    lines = text.splitlines(keepends=True)
    group = None
    changed = set()
    for i, line in enumerate(lines):
        if line.strip().startswith('['):
            group = line.strip()[1:-1]
        match = re.match(r'([^=\s]+)\s*=', line)
        if match and (section is None or group == section) and match[1] in values:
            if match[1] in changed:
                raise ValueError('duplicate user appearance key: ' + match[1])
            changed.add(match[1])
            lines[i] = match[1] + '=' + values[match[1]] + '\n'
    missing = [key + '=' + value + '\n' for key, value in values.items() if key not in changed]
    if missing:
        start = next((i + 1 for i, line in enumerate(lines) if line.strip() == '[' + str(section) + ']'), len(lines))
        lines[start:start] = missing
    if pending is None:
        raise ValueError('appearance writes require a checked plan')
    pending.append((path, ''.join(lines)))


def apply(home, mode):
    if home.is_symlink() or not home.is_dir() or home.resolve() == Path('/'):
        raise ValueError('user home must be a real directory')
    home = home.resolve()
    label = mode.title()
    icon = 'breeze-dark' if mode == 'dark' else 'breeze'
    pending = []
    update(home, '.gtkrc-2.0', {'gtk-theme-name': '"Xodus-' + label + '"',
                               'gtk-font-name': '"Noto Sans 10"',
                               'gtk-icon-theme-name': '"' + icon + '"',
                               'gtk-cursor-theme-name': '"breeze_cursors"'}, required=True, pending=pending)
    for version in ('3', '4'):
        update(home, '.config/gtk-' + version + '.0/settings.ini',
               {'gtk-theme-name': 'Xodus-' + label, 'gtk-font-name': 'Noto Sans 10',
                'gtk-icon-theme-name': icon, 'gtk-cursor-theme-name': 'breeze_cursors',
                'gtk-application-prefer-dark-theme': 'true' if mode == 'dark' else 'false'},
               'Settings', required=True, pending=pending)
    # Retain profile IDs, selected profile, shell command and custom profile choices.
    for name, scheme in (('Normal', 'Xodus Dark' if mode == 'dark' else 'Xodus Light'),
                         ('Fancy', 'Xodus Glass' if mode == 'dark' else 'Xodus Light Glass')):
        relative = '.local/share/konsole/pearOS ' + name + '.profile'
        path = home / relative
        if path.is_file() and not path.is_symlink():
            current = re.search(r'^ColorScheme=(.*)$', path.read_text(), re.M)
            if current and current[1] in ('WhiteOnBlack', 'Fancy Blur', 'Xodus Dark', 'Xodus Light', 'Xodus Glass', 'Xodus Light Glass'):
                update(home, relative, {'ColorScheme': scheme}, 'Appearance', pending=pending)
    # Inspect every destination before changing any user configuration.
    for path, text in pending:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('dark', 'light'), required=True)
    parser.add_argument('--home', type=Path, default=Path(os.environ['HOME']))
    args = parser.parse_args()
    try:
        apply(args.home, args.mode)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))

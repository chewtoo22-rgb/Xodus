#!/usr/bin/env python3
"""Apply original Xodus GTK/terminal defaults to an audited staged live root."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess

HERE = Path(__file__).resolve().parent
HOMES = ('etc/skel', 'home/liveuser')
HOME_FILES = (
    '.gtkrc-2.0', '.config/gtk-3.0/settings.ini', '.config/gtk-3.0/gtk.css',
    '.config/gtk-3.0/colors.css', '.config/gtk-4.0/settings.ini',
    '.config/gtk-4.0/gtk.css', '.config/gtk-4.0/colors.css',
    '.themes/pearOS-Dark/index.theme', '.themes/pearOS-Light/index.theme',
    '.local/share/konsole/pearOS Fancy.profile',
    '.local/share/konsole/pearOS Normal.profile',
    '.local/share/konsole/Fancy Blur.colorscheme',
)
SWITCHER = runpy.run_path(str(HERE / 'derive-theme-switcher.py'))
GLOBAL_INPUTS = ('usr/share/themes/pearOS/index.theme', 'usr/share/themes/pearOS-dark/index.theme', *SWITCHER['FILES'])
RUNTIME = 'usr/lib/xodus/apply-user-toolkit-mode'
EXECUTABLE_FILES = (RUNTIME, *(path for path in SWITCHER['SCRIPTS'] if not path.endswith('.json')))
RECEIPT = 'usr/lib/xodus/toolkit-source.json'
NOTICE_BASE = 'usr/share/licenses/xodus-toolkit/upstream'
PREFERENCES = {
    '.gtkrc-2.0': ('gtk-theme-name',),
    '.config/gtk-3.0/settings.ini': ('gtk-theme-name', 'gtk-application-prefer-dark-theme'),
    '.config/gtk-4.0/settings.ini': ('gtk-theme-name', 'gtk-application-prefer-dark-theme'),
}


def fail(message):
    raise ValueError('Xodus toolkit identity: ' + message)


def safe(root, relative, required=False):
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            fail('symlink in toolkit path: ' + relative)
        if candidate != path and candidate.exists() and not candidate.is_dir():
            fail('non-directory toolkit parent: ' + relative)
    if root not in path.resolve().parents or (path.exists() and not path.is_file()):
        fail('unsafe toolkit path: ' + relative)
    if required and not path.is_file():
        fail('missing toolkit file: ' + relative)
    if path.is_file() and path.stat().st_nlink != 1:
        fail('hardlink in toolkit path: ' + relative)
    return path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def key(text, name, replacement=None):
    matches = list(re.finditer(r'^' + re.escape(name) + r'=(.*)$', text, re.M))
    if len(matches) != 1:
        fail('duplicate or missing reviewed setting: ' + name)
    match = matches[0]
    value = match.group(1)
    if replacement is None:
        return value.strip('"')
    return text[:match.start()] + name + '=' + replacement + text[match.end():]


def normalize(relative, data):
    text = data.decode('utf-8')
    for name in PREFERENCES.get(relative, ()):
        value = key(text, name)
        allowed = ('pearOS-Dark', 'pearOS-Light') if name == 'gtk-theme-name' else ('true', 'false', '1', '0')
        if value not in allowed:
            fail('unreviewed toolkit preference: ' + relative + ': ' + name)
        text = key(text, name, '@REVIEWED_PREFERENCE@')
    return text.encode()


def checked_input(relative, data, lock):
    reference = relative
    for home in HOMES:
        if relative.startswith(home + '/'):
            reference = 'etc/skel/' + relative[len(home) + 1:]
            normalized_relative = relative[len(home) + 1:]
            break
    else:
        normalized_relative = relative
    row = lock['files'][reference]
    if sha(normalize(normalized_relative, data)) != row['normalized_sha256']:
        fail('audited package input changed: ' + relative)


def palette(mode):
    if mode == 'Dark':
        return {'bg': '#100B18', 'base': '#1A1323', 'fg': '#F6F2FF', 'border': '#44364F',
                'muted': '#A99EB8', 'accent': '#AD85F5', 'selected': '#AD85F5', 'selection_fg': '#100B18', 'link': '#CDB1FF'}
    return {'bg': '#F8F6FC', 'base': '#FFFFFF', 'fg': '#231F2F', 'border': '#D5C9E3',
            'muted': '#70627F', 'accent': '#7547C0', 'selected': '#7547C0', 'selection_fg': '#FFFFFF', 'link': '#7547C0'}


def css(mode, version='3'):
    p = palette(mode)
    names = {
        'theme_bg_color': p['bg'], 'theme_fg_color': p['fg'],
        'theme_base_color': p['base'], 'theme_text_color': p['fg'],
        'borders': p['border'], 'theme_selected_bg_color': p['selected'],
        'theme_selected_fg_color': p['selection_fg'], 'link_color': p['link'],
        'accent_color': p['accent'], 'accent_bg_color': p['selected'], 'accent_fg_color': p['selection_fg'],
        'window_bg_color': p['bg'], 'window_fg_color': p['fg'],
        'view_bg_color': p['base'], 'view_fg_color': p['fg'],
        'headerbar_bg_color': p['bg'], 'headerbar_fg_color': p['fg'],
        'card_bg_color': p['base'], 'card_fg_color': p['fg'], 'popover_bg_color': p['base'],
        'popover_fg_color': p['fg'], 'dialog_bg_color': p['bg'], 'dialog_fg_color': p['fg'],
    }
    return ('/* Original Xodus ' + mode + ' palette; SPDX-License-Identifier: MIT */\n' +
            ''.join('@define-color ' + name + ' ' + value + ';\n' for name, value in names.items()) +
            (HERE / 'common-gtk.css').read_text() +
            ('entry:focus-within { border-color: @theme_selected_bg_color; outline-color: @theme_selected_bg_color; }\n' if version == '4' else '')).encode()


def gtk2(mode):
    p = palette(mode)
    return f'''# Original Xodus GTK2 theme. SPDX-License-Identifier: MIT
style "xodus" {{
  font_name = "Noto Sans 10"
  bg[NORMAL] = "{p['bg']}"
  bg[PRELIGHT] = "{p['base']}"
  bg[ACTIVE] = "{p['selected']}"
  bg[SELECTED] = "{p['selected']}"
  fg[NORMAL] = "{p['fg']}"
  fg[PRELIGHT] = "{p['fg']}"
  fg[ACTIVE] = "{p['selection_fg']}"
  fg[SELECTED] = "{p['selection_fg']}"
  base[NORMAL] = "{p['base']}"
  base[SELECTED] = "{p['selected']}"
  text[NORMAL] = "{p['fg']}"
  text[SELECTED] = "{p['selection_fg']}"
  fg[INSENSITIVE] = "{p['muted']}"
  text[INSENSITIVE] = "{p['muted']}"
  xthickness = 3
  ythickness = 3
  engine "" {{}}
}}
widget_class "*" style "xodus"
widget "*" style "xodus"
'''.encode()


def terminal(glass=False, light=False):
    colors = ('16,11,24', '234,114,136', '127,210,159', '238,193,114',
              '159,168,245', '195,148,250', '115,205,214', '224,215,239')
    intense = ('100,84,119', '255,154,173', '168,232,188', '255,218,161',
               '195,202,255', '222,189,255', '167,233,237', '255,255,255')
    if light:
        colors = ('35,31,47', '165,37,66', '32,111,69', '133,86,18',
                  '57,65,166', '117,71,192', '23,106,118', '119,103,137')
        intense = ('77,62,97', '184,41,74', '27,122,72', '137,91,20',
                   '64,76,186', '130,75,205', '24,119,132', '35,31,47')
    parts = []
    surfaces = (('Background', '248,246,252'), ('BackgroundFaint', '255,255,255'),
                ('BackgroundIntense', '238,231,248'), ('Foreground', '35,31,47'),
                ('ForegroundFaint', '112,98,127'), ('ForegroundIntense', '77,45,133')) if light else (
                ('Background', '16,11,24'), ('BackgroundFaint', '26,19,35'),
                ('BackgroundIntense', '8,6,13'), ('Foreground', '246,242,255'),
                ('ForegroundFaint', '193,180,211'), ('ForegroundIntense', '222,189,255'))
    for name, color in surfaces:
        parts.append(f'[{name}]\nColor={color}\n')
    for index, (normal, bright) in enumerate(zip(colors, intense)):
        for suffix, color in (('', normal), ('Faint', normal), ('Intense', bright)):
            parts.append(f'[Color{index}{suffix}]\nColor={color}\n')
    label = ('Light Glass' if glass else 'Light') if light else ('Glass' if glass else 'Dark')
    parts.append('[General]\nDescription=Xodus ' + label +
                 '\nOpacity=' + ('0.94' if glass else '1') + '\nBlur=' + ('true' if glass else 'false') +
                 '\nColorRandomization=false\nWallpaper=\n')
    return '\n'.join(parts).encode()


def global_outputs():
    outputs = {}
    for mode in ('Dark', 'Light'):
        base = 'usr/share/themes/Xodus-' + mode
        outputs[base + '/index.theme'] = f'''[Desktop Entry]
Type=X-GNOME-Metatheme
Name=Xodus {mode}
Comment=Original Xodus GTK appearance
Encoding=UTF-8
[X-GNOME-Metatheme]
GtkTheme=Xodus-{mode}
'''.encode()
        outputs[base + '/gtk-2.0/gtkrc'] = gtk2(mode)
        for version in ('3', '4'):
            outputs[base + '/gtk-' + version + '.0/gtk.css'] = css(mode, version)
            outputs[base + '/gtk-' + version + '.0/gtk-dark.css'] = css('Dark', version)
    outputs['usr/share/konsole/Xodus Dark.colorscheme'] = terminal()
    outputs['usr/share/konsole/Xodus Glass.colorscheme'] = terminal(True)
    outputs['usr/share/konsole/Xodus Light.colorscheme'] = terminal(light=True)
    outputs['usr/share/konsole/Xodus Light Glass.colorscheme'] = terminal(True, light=True)
    outputs[RUNTIME] = (HERE / 'apply-user-toolkit-mode.py').read_bytes()
    outputs['usr/share/licenses/xodus-toolkit/LICENSE'] = (HERE / 'LICENSE').read_bytes()
    outputs['usr/share/licenses/xodus-toolkit/NOTICE'] = (
        'Xodus toolkit themes and terminal palettes are original MIT-licensed work.\n'
        'Input defaults come from pearos-settings26.7.0-4 (GPL3) and system-settings26.7.0-1 (GPLv3).\n'
        'Upstream source and author: https://github.com/pearOS-archlinux (Pear Software).\n'
        'Reviewed original selector, configuration, CSS and profile bytes are retained under upstream/.\n'
        'Existing installed package notices and licenses remain in place.\n').encode()
    return outputs


SYSTEM_FILES = tuple(sorted(global_outputs())) + GLOBAL_INPUTS + (RECEIPT,)
NOTICE_FILES = tuple(NOTICE_BASE + '/' + path for path in
                     (*GLOBAL_INPUTS, *(home + '/' + rel for home in HOMES for rel in HOME_FILES)))
TRANSFER_FILES = tuple(sorted(set(SYSTEM_FILES) | set(NOTICE_FILES) |
                             {'etc/skel/' + rel for rel in HOME_FILES}))
USER_CONFIGS = HOME_FILES
REFERENCE_FILES = tuple('overlay/identity/toolkit/' + path for path in (
    'apply-toolkit-identity.py', 'derive-theme-switcher.py', 'apply-user-toolkit-mode.py',
    'common-gtk.css', 'user-gtk3.css', 'user-gtk4.css', 'source.lock.json', 'LICENSE'))


def derive_inputs(originals):
    updates = global_outputs()
    for relative, data in originals.items():
        if relative in SWITCHER['FILES']:
            updates[relative] = SWITCHER['derive'](relative, data)
            continue
        text = data.decode('utf-8')
        suffix = next((relative[len(home) + 1:] for home in HOMES if relative.startswith(home + '/')), relative)
        if suffix == '.gtkrc-2.0':
            selected = key(text, 'gtk-theme-name').replace('pearOS-', 'Xodus-')
            text = key(text, 'gtk-theme-name', '"' + selected + '"')
            text = key(text, 'gtk-font-name', '"Noto Sans 10"')
        elif suffix.endswith('settings.ini'):
            selected = key(text, 'gtk-theme-name').replace('pearOS-', 'Xodus-')
            text = key(text, 'gtk-theme-name', selected)
            text = key(text, 'gtk-font-name', 'Noto Sans 10')
        elif suffix.endswith('index.theme'):
            mode = 'Dark' if 'dark' in relative.lower() else 'Light'
            text = key(text, 'Name', 'Xodus ' + mode)
            text = key(text, 'Comment', 'Xodus ' + mode + ' GTK appearance')
            text = key(text, 'GtkTheme', 'Xodus-' + mode)
        elif suffix.endswith('profile'):
            fancy = 'Fancy.profile' in relative
            text = key(text, 'Name', 'Xodus Glass' if fancy else 'Xodus Terminal')
            text = key(text, 'ColorScheme', 'Xodus Glass' if fancy else 'Xodus Dark')
            text = text.replace('[Appearance]\n', '[Appearance]\nFont=Noto Sans Mono,11,-1,5,400,0,0,0,0,0\n', 1)
        elif suffix.endswith('colorscheme'):
            updates[relative] = terminal(True)
            continue
        elif '/gtk-3.0/' in suffix and suffix.endswith(('gtk.css', 'colors.css')):
            updates[relative] = (HERE / 'user-gtk3.css').read_bytes() if suffix.endswith('/gtk.css') else b'/* Xodus accent is defined in gtk.css; theme surfaces follow the selected preference. */\n'
            continue
        elif '/gtk-4.0/' in suffix and suffix.endswith(('gtk.css', 'colors.css')):
            updates[relative] = (HERE / 'user-gtk4.css').read_bytes() if suffix.endswith('/gtk.css') else b'/* Xodus accent is defined in gtk.css; theme surfaces follow the selected preference. */\n'
            continue
        else:
            fail('unreviewed transform path: ' + relative)
        updates[relative] = text.encode()
    return updates


def apply(root, verify=False):
    if root.is_symlink() or not root.is_dir():
        fail('live root must be a real directory')
    root = root.resolve(strict=True)
    if root == Path('/'):
        fail('refusing the host root')
    lock = json.loads((HERE / 'source.lock.json').read_text())
    if not verify:
        for package, version in ((lock['package'], lock['version']), ('system-settings', lock['switcher']['version'])):
            result = subprocess.run(['arch-chroot', str(root), '/usr/bin/pacman', '-Q', package],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode or result.stdout.strip() != package + ' ' + version:
                fail('toolkit package version changed: ' + package)
    input_paths = (*GLOBAL_INPUTS, *(home + '/' + rel for home in HOMES for rel in HOME_FILES))
    originals = {}
    for relative in input_paths:
        source = NOTICE_BASE + '/' + relative if verify else relative
        data = safe(root, source, True).read_bytes()
        checked_input(relative, data, lock)
        originals[relative] = data
    updates = derive_inputs(originals)
    receipt = (json.dumps({'schema': 1, 'package': lock['package'], 'version': lock['version'],
                          'archive_sha256': lock['archive_sha256'],
                          'switcher': lock['switcher'],
                          'inputs': {path: sha(data) for path, data in sorted(originals.items())},
                          'outputs': {path: sha(data) for path, data in sorted(updates.items())}}, indent=2) + '\n').encode()
    updates.update({NOTICE_BASE + '/' + path: data for path, data in originals.items()})
    updates[RECEIPT] = receipt
    paths = {relative: safe(root, relative, verify) for relative in updates}
    if verify:
        for relative, data in updates.items():
            retained = paths[relative].read_bytes()
            # The separately audited desktop helper runs next and selects Breeze.
            # Admit only these exact key replacements, with every other byte fixed.
            alternatives = [data]
            if relative.endswith(('.gtkrc-2.0', '/settings.ini')) and relative in originals:
                for icon in ('breeze', 'breeze-dark'):
                    text = data.decode()
                    quoted = relative.endswith('.gtkrc-2.0')
                    for name, value in (('gtk-icon-theme-name', icon), ('gtk-cursor-theme-name', 'breeze_cursors')):
                        text = key(text, name, '"' + value + '"' if quoted else value)
                    if not quoted:
                        text = key(text, 'gtk-decoration-layout', ':minimize,maximize,close')
                    alternatives.append(text.encode())
            if retained not in alternatives:
                fail('retained toolkit bytes differ from reviewed derivation: ' + relative)
            if paths[relative].stat().st_mode & 0o777 != (0o755 if relative in EXECUTABLE_FILES else 0o644):
                fail('retained toolkit mode changed: ' + relative)
    else:
        if paths[RECEIPT].exists():
            fail('toolkit identity already applied')
        for relative, path in paths.items():
            if relative not in originals and path.exists():
                fail('new toolkit payload already exists: ' + relative)
        # All source hashes and output paths are checked before any mutation.
        for relative, data in updates.items():
            path = paths[relative]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o755 if relative in EXECUTABLE_FILES else 0o644)
    print(('Verified' if verify else 'Applied') + ' audited Xodus GTK and terminal appearance')


def verify(root, payload=None):
    """Verify against trusted source assets, including narrow desktop replacements."""
    global HERE, SWITCHER
    if payload is not None:
        HERE = Path(payload).resolve(strict=True)
        SWITCHER = runpy.run_path(str(HERE / 'derive-theme-switcher.py'))
    apply(Path(root), True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='?')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--list-reference-files', action='store_true')
    parser.add_argument('--list-transfer-files', action='store_true')
    args = parser.parse_args()
    try:
        if args.list_reference_files:
            print('\n'.join(REFERENCE_FILES))
        elif args.list_transfer_files:
            print('\n'.join(TRANSFER_FILES))
        elif args.root:
            apply(args.root, args.verify)
        else:
            parser.error('root is required')
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc))

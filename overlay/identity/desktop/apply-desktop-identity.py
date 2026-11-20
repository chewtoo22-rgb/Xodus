#!/usr/bin/env python3
"""Select supported KDE controls and remove inherited Mac styling defaults."""
import argparse
import hashlib
import json
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parent
CONFIGS = ('kdeglobals', 'kwinrc', 'kcminputrc', 'plasmarc')
GTK_CONFIGS = ('.gtkrc-2.0', '.config/gtk-3.0/settings.ini', '.config/gtk-4.0/settings.ini')
USER_CONFIGS = tuple('.config/' + name for name in CONFIGS) + GTK_CONFIGS
TRANSFER_FILES = ('usr/lib/xodus/desktop-identity.json', 'usr/share/licenses/xodus-desktop/NOTICE',
                  'usr/share/color-schemes/Xodus Light.colors') + tuple('etc/skel/' + name for name in USER_CONFIGS)
REFERENCE_FILES = ('apply-desktop-identity.py', 'upstream-inputs.json', 'expected-output.json', 'NOTICE', 'Xodus Light.colors')
DEPENDENCIES = (
    'usr/share/icons/breeze/index.theme',
    'usr/share/icons/breeze-dark/index.theme',
    'usr/share/icons/breeze_cursors/index.theme',
    'usr/lib/qt6/plugins/styles/breeze6.so',
    'usr/share/plasma/desktoptheme/default/metadata.json',
    'usr/share/plasma/look-and-feel/org.kde.breezedark.desktop/metadata.json',
)
DECORATION_PATHS = tuple('usr/lib/qt6/plugins/' + version + '/org.kde.breeze.so'
                         for version in ('org.kde.kdecoration2', 'org.kde.kdecoration3'))
SCAN_DIRS = DEPENDENCIES + DECORATION_PATHS


def checked(root, relative, required=False):
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink() or (candidate != path and candidate.exists() and not candidate.is_dir()):
            raise ValueError('Unsafe desktop identity path: ' + relative)
    if root not in path.resolve().parents or (path.exists() and not path.is_file()):
        raise ValueError('Desktop identity path escapes root: ' + relative)
    if required and not path.is_file():
        raise ValueError('Missing desktop input or dependency: ' + relative)
    return path


def replace(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Desktop selection layout changed: ' + before.strip())
    return text.replace(before, after, 1)


def color_tables(text, palette):
    def blocks(contents):
        current, result = None, {}
        for line in contents.splitlines(keepends=True):
            if line.startswith('[') and line.rstrip().endswith(']'):
                current = line.rstrip()
                if current in result:
                    raise ValueError('Duplicate color configuration group: ' + current)
                result[current] = ''
            if current is not None:
                result[current] += line
        return result
    scheme = blocks(palette)
    old = blocks(text)
    def selected(name):
        return name.startswith(('[Colors:', '[ColorEffects:')) or name == '[WM]'
    return ''.join(value for name, value in old.items() if not selected(name)) + ''.join(
        value for name, value in scheme.items() if selected(name))


def outputs(contents, palette):
    result = dict(contents)
    for before, after in (
        ('[Icons]\nTheme=pearOS-blue\n', '[Icons]\nTheme=breeze-dark\n'),
        ('LookAndFeelPackage=com.github.vinceliuice.WhiteSur-dark\n', 'LookAndFeelPackage=org.kde.breezedark.desktop\n'),
        ('widgetStyle=kvantum\n', 'widgetStyle=Breeze\n'),
        ('[Wallpaper]\nImage=pearOS\n', '[Wallpaper]\nImage=/usr/share/wallpapers/Xodus/xodus-wallpaper.png\n'),
    ):
        result['kdeglobals'] = replace(result['kdeglobals'], before, after)
    result['kcminputrc'] = replace(result['kcminputrc'], 'cursorTheme=pearOS\n', 'cursorTheme=breeze_cursors\n')
    result['plasmarc'] = replace(result['plasmarc'], '[Theme]\nname=pearOS-dark\n', '[Theme]\nname=default\n')
    before = ('[org.kde.kdecoration2]\nBorderSize=None\nBorderSizeAuto=false\n'
              'ButtonsOnLeft=XIA\nButtonsOnRight=\nLibrary=org.kde.kwin.aurorae\n'
              'Theme=__aurorae__svg__pearOS-dark\nlibrary=breezeenhanced\ntheme=pearOS\n')
    after = ('[org.kde.kdecoration2]\nBorderSize=Normal\nBorderSizeAuto=false\n'
             'ButtonsOnLeft=M\nButtonsOnRight=IAX\nLibrary=org.kde.breeze\n'
             'Theme=Breeze\n')
    result['kwinrc'] = replace(result['kwinrc'], before, after)
    result['kdeglobals'] = color_tables(result['kdeglobals'], palette)
    return result


def apply(root, payload=PAYLOAD):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Desktop staging root must be a real directory')
    root = root.resolve(strict=True)
    if root == Path('/'):
        raise ValueError('Refusing the host root')
    lock = json.loads((payload / 'upstream-inputs.json').read_text())
    if lock.get('schema') != 1 or set(lock['files']) != set(CONFIGS):
        raise ValueError('Desktop source inventory changed')
    for relative in DEPENDENCIES:
        checked(root, relative, True)
    decoration = [checked(root, relative) for relative in DECORATION_PATHS]
    if not any(path.is_file() for path in decoration):
        raise ValueError('Breeze window decoration plugin is missing')
    writes = []
    receipt = checked(root, 'usr/lib/xodus/desktop-identity.json')
    if receipt.exists():
        raise ValueError('Desktop identity already staged')
    for home in ('etc/skel', 'home/liveuser'):
        contents = {}
        for name in CONFIGS:
            path = checked(root, home + '/.config/' + name, True)
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != lock['files'][name]:
                raise ValueError('Desktop package input changed: ' + home + '/' + name)
            contents[name] = data.decode('utf-8')
        palette = checked(root, 'usr/share/color-schemes/Xodus.colors', True).read_text()
        expected = json.loads((payload / 'expected-output.json').read_text())
        for name, text in outputs(contents, palette).items():
            if hashlib.sha256(text.encode()).hexdigest() != expected[name]:
                raise ValueError('Desktop prepared output differs from reviewed source: ' + name)
            writes.append((checked(root, home + '/.config/' + name, True), text.encode()))
        for name in GTK_CONFIGS:
            path = checked(root, home + '/' + name, True)
            text = path.read_text()
            if name == '.gtkrc-2.0':
                text = replace(text, 'gtk-cursor-theme-name="pearOS-cursors"\n', 'gtk-cursor-theme-name="breeze_cursors"\n')
                text = replace(text, 'gtk-icon-theme-name="pearOS-light"\n', 'gtk-icon-theme-name="breeze"\n')
            else:
                text = replace(text, 'gtk-cursor-theme-name=pearOS\n', 'gtk-cursor-theme-name=breeze_cursors\n')
                text = replace(text, 'gtk-icon-theme-name=pearOS\n', 'gtk-icon-theme-name=breeze-dark\n')
                text = replace(text, 'gtk-decoration-layout=close,minimize,maximize:\n', 'gtk-decoration-layout=:minimize,maximize,close\n')
            writes.append((path, text.encode()))
    light = checked(root, 'usr/share/color-schemes/Xodus Light.colors')
    if light.exists():
        raise ValueError('Xodus Light colorscheme already staged')
    manifest = {'schema': 1, 'source': lock,
                'files': {path.relative_to(root).as_posix(): hashlib.sha256(data).hexdigest()
                          for path, data in writes}}
    notice = checked(root, 'usr/share/licenses/xodus-desktop/NOTICE')
    if notice.exists():
        raise ValueError('Desktop identity NOTICE already exists')
    writes += [(light, (payload / 'Xodus Light.colors').read_bytes()),
               (notice, (payload / 'NOTICE').read_bytes()),
               (receipt, (json.dumps(manifest, indent=2) + '\n').encode())]
    for path, data in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o644)
    print('Applied Xodus desktop controls, icons and cursor selections')


def verify(root, payload=PAYLOAD):
    root = root.resolve(strict=True)
    if root == Path('/'):
        raise ValueError('Refusing the host root')
    dependencies = {relative for relative in DEPENDENCIES}
    for relative in dependencies:
        checked(root, relative, True)
    decoration = {relative for relative in DECORATION_PATHS if checked(root, relative).is_file()}
    if not decoration:
        raise ValueError('Breeze window decoration plugin is missing')
    expected = json.loads((payload / 'expected-output.json').read_text())
    lock = json.loads((payload / 'upstream-inputs.json').read_text())
    receipt = json.loads(checked(root, 'usr/lib/xodus/desktop-identity.json', True).read_text())
    if set(receipt) != {'schema', 'source', 'files'} or receipt['schema'] != 1 or receipt['source'] != lock:
        raise ValueError('Desktop identity receipt source changed')
    paths = {home + '/' + name for home in ('etc/skel', 'home/liveuser') for name in USER_CONFIGS}
    if set(receipt['files']) != paths:
        raise ValueError('Desktop identity receipt inventory changed')
    for relative in paths:
        data = checked(root, relative, True).read_bytes()
        if hashlib.sha256(data).hexdigest() != receipt['files'][relative]:
            raise ValueError('Desktop identity retained file changed: ' + relative)
        if relative.endswith(tuple('/' + name for name in CONFIGS)):
            if hashlib.sha256(data).hexdigest() != expected[Path(relative).name]:
                raise ValueError('Desktop selections differ from source: ' + relative)
    for target, reference in (('usr/share/licenses/xodus-desktop/NOTICE', 'NOTICE'),
                              ('usr/share/color-schemes/Xodus Light.colors', 'Xodus Light.colors')):
        if checked(root, target, True).read_bytes() != (payload / reference).read_bytes():
            raise ValueError('Desktop payload differs from source: ' + target)
    return sorted(paths | dependencies | decoration | {'usr/lib/xodus/desktop-identity.json', 'usr/share/licenses/xodus-desktop/NOTICE',
                           'usr/share/color-schemes/Xodus Light.colors'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    try:
        if args.verify:
            verify(args.root)
        else:
            apply(args.root)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc))

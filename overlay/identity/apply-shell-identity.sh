#!/usr/bin/env bash
set -euo pipefail

live_root=${1:-}
[[ -n "$live_root" && -d "$live_root" && "$live_root" != / ]] || {
  echo 'usage: apply-shell-identity.sh <live-root>' >&2
  exit 64
}

# Run after the package install and apply-visible-identity.sh. The package
# files do not exist in the source archiso profile. Every expected input is
# checked before any change is written, so a changed package layout fails the
# build instead of leaving an incomplete Xodus shell.
shell_payload=${2:-$(dirname "${BASH_SOURCE[0]}")/shell}
python3 - "$live_root" "$shell_payload" <<'PY'
from pathlib import Path
import json
import re
import sys

root = Path(sys.argv[1]).resolve(strict=True)
if root == Path('/'):
    raise SystemExit('refusing to edit the filesystem root')

payload = Path(sys.argv[2]).resolve(strict=True)
if not payload.is_dir():
    raise SystemExit('Xodus shell payload is not a directory')

wallpaper = 'file:///usr/share/wallpapers/Xodus/xodus-wallpaper.png'
app_icon = 'file:///usr/share/pixmaps/xodus-app-icon.png'
updates: dict[Path, str] = {}


def checked_file(relative: str) -> Path:
    path = root / relative
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        raise SystemExit(f'expected regular live-root file is missing or unsafe: {relative}')
    return path


def new_file(relative: str) -> Path:
    path = root / relative
    if path.exists() or path.is_symlink():
        raise SystemExit(f'Xodus shell output already exists: {relative}')
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise SystemExit(f'unsafe Xodus shell output parent: {relative}')
    if root not in path.resolve().parents:
        raise SystemExit(f'Xodus shell output escapes live root: {relative}')
    return path


for asset in ('usr/share/wallpapers/Xodus/xodus-wallpaper.png',
              'usr/share/pixmaps/xodus-app-icon.png'):
    path = checked_file(asset)
    if path.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
        raise SystemExit(f'Xodus image is not a PNG: {asset}')


def source(relative: str) -> str:
    path = checked_file(relative)
    if path not in updates:
        updates[path] = path.read_bytes().decode('utf-8')
    return updates[path]


def replace(relative: str, old: str, new: str, count: int = 1) -> None:
    path = checked_file(relative)
    contents = source(relative)
    if contents.count(old) != count:
        raise SystemExit(f'unexpected shell identity layout: {relative}: {old[:70]!r}')
    updates[path] = contents.replace(old, new)


def replace_line(relative: str, old: str, new: str) -> None:
    path = checked_file(relative)
    lines = source(relative).splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.rstrip('\r\n') == old]
    if len(matches) != 1:
        raise SystemExit(f'unexpected shell identity line: {relative}: {old!r}')
    i = matches[0]
    newline = lines[i][len(old):]
    lines[i] = new + newline
    updates[path] = ''.join(lines)


def metadata(relative: str, expected: dict[str, str], changed: dict[str, str]) -> None:
    path = checked_file(relative)
    original = source(relative)
    try:
        document = json.loads(original)
        plugin = document['KPlugin']
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SystemExit(f'invalid Plasma metadata: {relative}: {exc}') from exc
    for key, value in expected.items():
        if plugin.get(key) != value:
            raise SystemExit(f'unexpected Plasma metadata {key}: {relative}')
    for key, value in changed.items():
        plugin[key] = value
    if any(key.startswith('Name[') and re.search(r'pear|pinder', str(value), re.I)
           for key, value in plugin.items()):
        raise SystemExit(f'unreviewed localized Plasma branding: {relative}')
    # Authors, copyright, licenses, upstream URLs and stable plugin IDs are
    # deliberately preserved as source attribution and runtime identifiers.
    updates[path] = json.dumps(document, ensure_ascii=False, indent=4) + '\n'


for home in ('etc/skel', 'home/liveuser'):
    config = f'{home}/.config/'
    lock = config + 'kscreenlockerrc'
    replace_line(lock,
                 'Image=/usr/share/extras/wallpapers/Default/dark-mode.jpg',
                 'Image=/usr/share/wallpapers/Xodus/xodus-wallpaper.png')
    replace_line(lock,
                 'PreviewImage=/usr/share/extras/wallpapers/Default/dark-mode.jpg',
                 'PreviewImage=/usr/share/wallpapers/Xodus/xodus-wallpaper.png')

    for name in ('plasma-org.kde.plasma.desktop-appletsrc',
                 'plasma-org.kde.plasma.desktop-appletsrc.bak'):
        relative = config + name
        replace(relative,
                'PreviewImage=/usr/share/wallpapers/pearOS-dark/default.jpg',
                'PreviewImage=/usr/share/wallpapers/Xodus/xodus-wallpaper.png')
        replace(relative, 'noActivityText=Pinder  Pinder\\s',
                'noActivityText=Xodus\\s')
        path = checked_file(relative)
        lines = source(relative).splitlines(keepends=True)
        widget_lines = [i for i, line in enumerate(lines) if line.startswith('panelWidgets=')]
        if len(widget_lines) != 1:
            raise SystemExit(f'unexpected panel widget inventory: {relative}')
        index = widget_lines[0]
        raw = lines[index].rstrip('\r\n')
        newline = lines[index][len(raw):]
        try:
            widgets = json.loads(raw.split('=', 1)[1])
        except (ValueError, TypeError) as exc:
            raise SystemExit(f'invalid panel widget inventory: {relative}: {exc}') from exc
        titles = {
            'xyz.pearos.pearmenu': ('Pear Menu', 'Xodus Menu'),
            'PearAppTitle': ('Pear App Title', 'Xodus App Title'),
            'org.kde.plasma.appmenu': ('pearOS Global Menu', 'Xodus Global Menu'),
            'PearPrivacy': ('PearPrivacy', 'Xodus Privacy'),
            'PearClock': ('PearClock', 'Xodus Clock'),
        }
        for widget_id, (old, new) in titles.items():
            matches = [widget for widget in widgets
                       if widget.get('name') == widget_id]
            if len(matches) != 1 or matches[0].get('title') != old:
                raise SystemExit(f'unexpected panel widget {widget_id}: {relative}')
            matches[0]['title'] = new
        menu = next(widget for widget in widgets
                    if widget.get('name') == 'xyz.pearos.pearmenu')
        if menu.get('icon') != 'file:///usr/share/extras/drawing.svg':
            raise SystemExit(f'unexpected menu icon: {relative}')
        menu['icon'] = app_icon
        lines[index] = 'panelWidgets=' + json.dumps(
            widgets, ensure_ascii=False, separators=(',', ':')) + newline
        updates[path] = ''.join(lines)

    replace(config + 'filer-topbar-appletsrc',
            'noActivityText=Pinder  Pinder\\s', 'noActivityText=Xodus\\s')
    replace_line(config + 'ksplashrc', 'Theme=pearOS', 'Theme=pearOS')
    globals_file = config + 'kdeglobals'
    replace_line(globals_file, 'ColorScheme=pearOS-dark', 'ColorScheme=Xodus')
    replace_line(globals_file, 'ColorSchemeHash=79296561e8832ef612d7c1138272b1e03e6ba66d', '')
    replace_line(globals_file, 'AccentColor=61,174,233',
                 'AccentColor=173,133,245')
    replace_line(globals_file, 'LastUsedCustomAccentColor=61,174,233',
                 'LastUsedCustomAccentColor=173,133,245')
    replace(globals_file, 'MuternVF Text Regular', 'Noto Sans', count=5)
    replace_line(globals_file, 'fixed=Noto Sans,10,-1,5,50,0,0,0,0,0',
                 'fixed=Noto Sans Mono,10,-1,5,50,0,0,0,0,0')
    replace_line(globals_file,
                 'smallestReadableFont=Mutern VF,8,-1,5,510,0,0,0,0,0,0,0,0,0,0,1,Text Medium,0,0',
                 'smallestReadableFont=Noto Sans,8,-1,5,400,0,0,0,0,0,0,0,0,0,0,1,Regular,0,0')

# The active SDDM package keeps its upstream theme identifier; only the
# presented background and selectable label change. Its QML otherwise uses
# upstream controls and continues to carry its original license metadata.
for variant, label in (('pearOS-dark', 'Xodus Login Dark'),
                       ('pearOS', 'Xodus Login Light')):
    base = f'usr/share/sddm/themes/{variant}/'
    replace(base + 'Main.qml',
            'source: "file:///usr/share/extras/background.jpg"',
            f'source: "{wallpaper}"')
    replace(base + 'Main.qml',
            'source = "file:///usr/share/extras/background.png"',
            f'source = "{wallpaper}"')
    replace(base + 'theme.conf',
            'background=file:///usr/share/extras/background.jpg',
            f'background={wallpaper}')
    replace(base + 'theme.conf.user', 'background=background.jpg',
            f'background={wallpaper}')
    old_name = 'pearOS SDDM Dark' if variant.endswith('-dark') else 'pearOS SDDM'
    replace_line(base + 'metadata.desktop', f'Name={old_name}',
                 f'Name={label}')
    replace_line(base + 'metadata.desktop',
                 f'Description={old_name} 2025.10.27',
                 f'Description={label} theme for Xodus')

sddm_config_dir = root / 'etc/sddm.conf.d'
if (not sddm_config_dir.is_dir() or sddm_config_dir.is_symlink()
        or root not in sddm_config_dir.resolve().parents):
    raise SystemExit('expected safe SDDM config directory is missing')
for candidate in (root / 'etc/sddm.conf', *sddm_config_dir.glob('*.conf')):
    if candidate.exists() or candidate.is_symlink():
        if candidate.is_symlink() or not candidate.is_file():
            raise SystemExit(f'unsafe SDDM config: {candidate}')
        if re.search(r'^\s*Current\s*=', candidate.read_text(), re.M):
            raise SystemExit(f'unreviewed SDDM theme selection: {candidate}')
sddm_selection = sddm_config_dir / '20-xodus-theme.conf'
if sddm_selection.exists() or sddm_selection.is_symlink():
    raise SystemExit('Xodus SDDM selection already exists')
updates[sddm_selection] = '[Theme]\nCurrent=Xodus\n'

# Original login UI uses only QtQuick Controls and SDDM's authentication API.
# Keep the upstream package installed for its dependencies and attribution.
new_theme = root / 'usr/share/sddm/themes/Xodus'
if new_theme.exists() or new_theme.is_symlink():
    raise SystemExit('Xodus SDDM theme already exists')
if new_theme.parent.is_symlink() or root not in new_theme.parent.resolve().parents:
    raise SystemExit('unsafe SDDM theme parent')
for name in ('Main.qml', 'metadata.desktop', 'theme.conf'):
    source_path = payload / 'sddm' / name
    if source_path.is_symlink() or not source_path.is_file() or payload not in source_path.resolve().parents:
        raise SystemExit(f'missing or unsafe Xodus login payload: {name}')
    updates[new_file(f'usr/share/sddm/themes/Xodus/{name}')] = source_path.read_text(encoding='utf-8')
license_path = payload / 'LICENSE'
if license_path.is_symlink() or not license_path.is_file():
    raise SystemExit('missing or unsafe Xodus login license')
updates[new_file('usr/share/sddm/themes/Xodus/LICENSE')] = license_path.read_text(encoding='utf-8')
updates[new_file('usr/share/licenses/xodus-shell/LICENSE')] = license_path.read_text(encoding='utf-8')
colors_payload = payload / 'Xodus.colors'
if colors_payload.is_symlink() or not colors_payload.is_file():
    raise SystemExit('missing or unsafe Xodus color scheme payload')
updates[new_file('usr/share/color-schemes/Xodus.colors')] = colors_payload.read_text(encoding='utf-8')

# KDE's session splash is a separate stage after login. The upstream QML
# references an undefined bottomRect; replace it with an original stage-aware
# layout. Preserve its other installed source and license metadata.
splash_payload = payload / 'Splash.qml'
if splash_payload.is_symlink() or not splash_payload.is_file():
    raise SystemExit('missing or unsafe Xodus session splash payload')
xodus_splash = splash_payload.read_text(encoding='utf-8')
for variant, label in (('pearOS-dark', 'Xodus Session Dark'),
                       ('pearOS', 'Xodus Session Light')):
    base = f'usr/share/plasma/look-and-feel/{variant}/'
    splash = base + 'contents/splash/Splash.qml'
    original = source(splash)
    for marker in ('Copyright 2018 notsag',
                   'source: "images/background.png"',
                   'source: "images/drawing.svg"',
                   'target: bottomRect'):
        if original.count(marker) != 1:
            raise SystemExit(f'unexpected upstream Plasma splash layout: {splash}')
    updates[checked_file(splash)] = xodus_splash
    expected_name = 'pearOS Splash Theme for Plasma'
    metadata(base + 'metadata.json',
             {'Name': expected_name, 'Description': 'Fedora Linux Splash Screen For Plasma 6'},
             {'Name': label, 'Description': 'Xodus Plasma session splash'})

widget_names = {
    'PearAppTitle': ('Pear App Title', 'Xodus App Title'),
    'PearClock': ('PearClock', 'Xodus Clock'),
    'PearCalendar': ('Calendar Widget', 'Xodus Calendar'),
    'PearControlCentre': ('PearControlCentre', 'Xodus Control Center'),
    'PearFinder': ('PearFinder', 'Xodus Files'),
    'PearFolderArc': ('PearFolderArc', 'Xodus Downloads'),
    'PearLauncher': ('Pear Launcher', 'Xodus Launcher'),
    'PearPrivacy': ('PearPrivacy', 'Xodus Privacy'),
    'PearTaskManager': ('Pear Task Manager', 'Xodus Task Manager'),
    'PearTrash': ('Pearcan', 'Xodus Trash'),
    'PearWeather': ('PearWeather', 'Xodus Weather'),
    'PearDock': ('Pear Dock', 'Xodus Dock'),
}
for widget, (old, new) in widget_names.items():
    relative = f'usr/share/plasma/plasmoids/{widget}/metadata.json'
    changes = {'Name': new}
    if widget == 'PearLauncher':
        changes.update(Description='Application launcher for Xodus',
                       Icon='/usr/share/pixmaps/xodus-app-icon.png')
    if widget == 'PearControlCentre':
        changes['Description'] = 'Xodus control center based on the work of prayag2'
    if widget == 'PearFolderArc':
        changes['Description'] = 'Downloads fan for Xodus'
    if widget == 'PearTrash':
        changes['Description'] = 'Trash widget for Xodus'
    metadata(relative, {'Name': old}, changes)

menu_base = 'usr/share/plasma/plasmoids/xyz.pearos.pearmenu/'
metadata(menu_base + 'metadata.json',
         {'Name': 'Pear Menu', 'Name[be]': 'Мэню Pear',
          'Icon': 'file:///usr/share/extras/drawing.svg'},
         {'Name': 'Xodus Menu', 'Name[be]': 'Xodus',
          'Description': 'Xodus application and session menu based on darwin-menu',
          'Icon': app_icon})
replace(menu_base + 'contents/config/main.xml',
        'file:///usr/share/extras/drawing.svg', app_icon, count=2)
replace(menu_base + 'contents/ui/MainMenuButton.qml',
        'i18n("About This Pear")', 'i18n("About Xodus")')

# These are presented defaults and tooltips, not runtime plugin identifiers.
replace('usr/share/plasma/plasmoids/PearDock/contents/ui/integrations/PearFinder.qml',
        'readonly property string title: i18n("Pinder")',
        'readonly property string title: i18n("Files")')
replace('usr/share/plasma/plasmoids/PearAppTitle/contents/config/main.xml',
        '<default>Pinder</default>', '<default>Xodus</default>', count=2)
replace('usr/share/plasma/plasmoids/PearAppTitle/contents/ui/config/ConfigAppearance.qml',
        'text: "Pinder"', 'text: "Xodus"')
replace('usr/share/plasma/plasmoids/PearAppTitle/contents/ui/config/ConfigAppearance.qml',
        "Text to display when no application is running. If set to 'Pinder', will show 'Pinder' (bold) + ' Operating System' (non bold) + menu buttons (File, Edit, View, Go, Window, Help).",
        'Text to display when no application is running.')
replace('usr/share/plasma/plasmoids/PearLauncher/contents/ui/main.qml',
        'Plasmoid.icon: Qt.resolvedUrl("icons/appicons/launchpad_light.png")',
        f'Plasmoid.icon: "{app_icon}"')
replace('usr/share/plasma/plasmoids/PearLauncher/contents/config/main.xml',
        '<default>start-here-kde-symbolic</default>', f'<default>{app_icon}</default>')
replace('usr/share/plasma/plasmoids/PearDock/contents/ui/integrations/PearLauncher.qml',
        'source: Qt.resolvedUrl("icons/appicons/launchpad_light.png")',
        f'source: "{app_icon}"')

for variant, name, old_name, old_metadata_name, description in (
    ('pearOS-dark', 'Xodus Dark', 'pearOS-dark', 'pearOS-dark',
     'Dark Theme for pearOS'),
    ('pearOS', 'Xodus Light', 'pearOS', 'pearOS-Light',
     'pearOS Light theme'),
):
    theme = f'usr/share/plasma/desktoptheme/{variant}/'
    metadata(theme + 'metadata.json', {'Name': old_metadata_name},
             {'Name': name, 'Description': f'{name} desktop theme for Xodus'})
    replace_line(theme + 'metadata.desktop', f'Name={old_name}',
                 f'Name={name}')
    replace_line(theme + 'metadata.desktop', f'Comment={description}',
                 f'Comment={name} desktop theme for Xodus')
    replace_line(f'usr/share/color-schemes/{variant}.colors',
                 f'Name={old_name}', f'Name={name}')
    replace_line(f'usr/share/aurorae/themes/{variant}/metadata.desktop',
                 f'Name={old_name}', f'Name={name} Window Borders')

replace_line('usr/share/sounds/pearOS-sounds/index.theme',
             'Name=pearOS', 'Name=Xodus Sounds')

# The package's desktop launcher is also copied to each user's autostart.
for relative in ('usr/share/applications/pearos-notch.desktop',
                 'etc/skel/.config/autostart/pearos-notch.desktop',
                 'home/liveuser/.config/autostart/pearos-notch.desktop'):
    replace(relative, 'Name=Notch', 'Name=Xodus Notch')
    replace(relative, 'Comment=Notch', 'Comment=Xodus status and media controls')
    replace(relative, 'Icon=pearos-notch',
            'Icon=/usr/share/pixmaps/xodus-app-icon.png')

for path, contents in updates.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents.encode('utf-8'))

print(f'Applied Xodus shell identity to {len(updates)} staged desktop files')
PY

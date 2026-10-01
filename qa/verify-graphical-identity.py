#!/usr/bin/env python3
"""Validate graphical payload retained in a staged or extracted Xodus root."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import stat
import sys


COMPONENT_HELPERS = {'desktop': 'apply-desktop-identity.py', 'toolkit': 'apply-toolkit-identity.py',
                     'control-center': 'apply-control-center-identity.py', 'dock': 'apply-dock-identity.py'}


def component_helpers(repo):
    result = {}
    for name, filename in COMPONENT_HELPERS.items():
        path = repo / 'overlay/identity' / name / filename
        spec = importlib.util.spec_from_file_location('xodus_graphical_' + name.replace('-', '_'), path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        result[name] = module
    return result


SOURCE_REPO = Path(__file__).resolve().parents[1]
COMPONENTS = component_helpers(SOURCE_REPO)
COMPONENT_REFERENCES = set()
COMPONENT_PATHS = set()
for component, module in COMPONENTS.items():
    directory = SOURCE_REPO / 'overlay/identity' / component
    references = getattr(module, 'REFERENCE_FILES', None)
    if references is None:
        references = [path.relative_to(SOURCE_REPO).as_posix() for path in directory.rglob('*')
                      if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc']
    for reference in references:
        COMPONENT_REFERENCES.add(reference if reference.startswith('overlay/') else 'overlay/identity/' + component + '/' + reference)
    COMPONENT_PATHS.update(module.TRANSFER_FILES)
    for relative in getattr(module, 'USER_CONFIGS', ()):
        if relative.startswith('.'):
            COMPONENT_PATHS.update(home + '/' + relative for home in ('etc/skel', 'home/liveuser'))
        else:
            COMPONENT_PATHS.add(relative)
    COMPONENT_PATHS.update(getattr(module, 'SCAN_DIRS', ()))
COMPONENT_PATHS.add('usr/share/plasma/plasmoids/PearControlCentre')
COMPONENT_PATHS.add('usr/share/plasma/plasmoids/PearDock/contents/skins')


ASSET_FILES = {
    'usr/share/wallpapers/Xodus/xodus-wallpaper.png': 'overlay/identity/assets/xodus-wallpaper.png',
    'usr/share/pixmaps/xodus-app-icon.png': 'overlay/identity/assets/xodus-app-icon.png',
}
TEXT_FILES = {
    'usr/share/sddm/themes/Xodus/Main.qml': 'overlay/identity/shell/sddm/Main.qml',
    'usr/share/sddm/themes/Xodus/metadata.desktop': 'overlay/identity/shell/sddm/metadata.desktop',
    'usr/share/sddm/themes/Xodus/theme.conf': 'overlay/identity/shell/sddm/theme.conf',
    'usr/share/sddm/themes/Xodus/LICENSE': 'overlay/identity/shell/LICENSE',
    'usr/share/licenses/xodus-shell/LICENSE': 'overlay/identity/shell/LICENSE',
    'usr/share/color-schemes/Xodus.colors': 'overlay/identity/shell/Xodus.colors',
    'usr/share/plasma/look-and-feel/pearOS/contents/splash/Splash.qml': 'overlay/identity/shell/Splash.qml',
    'usr/share/plasma/look-and-feel/pearOS-dark/contents/splash/Splash.qml': 'overlay/identity/shell/Splash.qml',
}
SETTINGS_LAUNCHER = ('[Desktop Entry]\nType=Application\nName=Xodus Settings\n'
    'Comment=Configure your Xodus desktop and devices\nExec=systemsettings1\n'
    'Icon=/usr/share/pixmaps/xodus-app-icon.png\nStartupWMClass=xodus-settings\n'
    'Categories=Settings;System;\nTerminal=false\n')
WELCOME_LAUNCHER = ('[Desktop Entry]\nType=Application\nName=Xodus Welcome\n'
    'GenericName=Welcome to Xodus\nComment=Start exploring the Xodus desktop\n'
    'Exec=/usr/lib/xodus/xodus-welcome\nIcon=/usr/share/pixmaps/xodus-app-icon.png\n'
    'Terminal=false\nCategories=System;\nStartupNotify=true\n')
WALLPAPER = '/usr/share/wallpapers/Xodus/xodus-wallpaper.png'
REFERENCE_FILES = sorted(set(ASSET_FILES.values()) | set(TEXT_FILES.values()) | {
    'overlay/identity/settings/source.lock.json',
    'overlay/identity/settings/release-source.lock.json',
    'overlay/identity/settings/upstream-os-release',
} | COMPONENT_REFERENCES)
# Keep all SDDM configuration entries so a competing late theme cannot be
# hidden by extracting only the Xodus drop-in. These paths are relative to the
# squashfs root and may be supplied directly to unsquashfs.
EXTRACTION_PATHS = sorted(set(ASSET_FILES) | set(TEXT_FILES) | COMPONENT_PATHS | {
    'usr/lib/xodus/xodus-welcome', 'usr/lib/xodus/xodus-settings',
    'usr/lib/xodus/settings-source.json', 'usr/lib/xodus/release-source.json',
    'usr/lib/xodus/upstream-os-release', 'usr/lib/xodus/upstream-etc-os-release',
    'usr/bin/systemsettings1', 'usr/bin/system-overview',
    'usr/share/applications/pearos-systemsettings.desktop',
    'usr/share/applications/xodus-settings.desktop',
    'usr/share/applications/xodus-welcome.desktop', 'usr/share/applications/welcome.desktop',
    'usr/share/licenses/xodus-settings/NOTICE', 'usr/share/licenses/xodus-settings/upstream-license.txt',
    'usr/lib/os-release', 'etc/os-release', 'etc/sddm.conf', 'etc/sddm.conf.d',
} | {
    home + '/.config/' + name
    for home in ('etc/skel', 'home/liveuser')
    for name in ('autostart/xodus-welcome.desktop', 'autostart/welcome.desktop',
                 'plasma-org.kde.plasma.desktop-appletsrc', 'plasma-org.kde.plasma.desktop-appletsrc.bak',
                 'kscreenlockerrc', 'kdeglobals', 'ksplashrc')
} | {
    'usr/share/plasma/look-and-feel/' + variant + '/metadata.json'
    for variant in ('pearOS', 'pearOS-dark')
})


class IdentityError(ValueError):
    pass


def verify(root, repo):
    if root.is_symlink() or not root.is_dir():
        raise IdentityError('Graphical root must be a real directory')
    root = root.resolve()
    repo = repo.resolve()
    if root == Path('/'):
        raise IdentityError('Refusing the host root')
    checked = []
    def regular(relative):
        path = root / relative
        for component in (path, *path.parents):
            if component == root:
                break
            if component.is_symlink():
                raise IdentityError('Unsafe graphical symlink: ' + relative)
        if not path.is_file() or root not in path.resolve().parents:
            raise IdentityError('Missing graphical payload: ' + relative)
        checked.append(relative)
        return path
    def exact(relative, expected, mode=None):
        path = regular(relative)
        actual = path.read_bytes()
        if actual != expected:
            raise IdentityError('Graphical bytes differ from source: ' + relative)
        if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
            raise IdentityError('Graphical mode differs from contract: ' + relative)
    def text(relative):
        try:
            return regular(relative).read_text(encoding='utf-8')
        except UnicodeDecodeError as exc:
            raise IdentityError('Graphical text is not UTF-8: ' + relative) from exc
    def line_count(relative, contents, line, count=1):
        if contents.splitlines().count(line) != count:
            raise IdentityError('Graphical selection differs: ' + relative + ': ' + line)
    def binary(relative):
        path = regular(relative)
        with path.open('rb') as handle:
            header = handle.read(20)
        # ELF64, little endian, x86-64 machine; both apps are native binaries.
        if (len(header) < 20 or header[:7] != b'\x7fELF\x02\x01\x01'
                or header[18:20] != b'\x3e\x00'):
            raise IdentityError('Graphical app is not a native x86-64 ELF: ' + relative)
        if stat.S_IMODE(path.stat().st_mode) != 0o755:
            raise IdentityError('Graphical app mode must be 0755: ' + relative)
    def release_file(relative):
        guest_name = '/' + relative
        seen = set()
        while guest_name not in seen:
            seen.add(guest_name)
            if guest_name not in ('/etc/os-release', '/usr/lib/os-release'):
                raise IdentityError('Release symlink escapes its audited target: ' + guest_name)
            path = root / guest_name.lstrip('/')
            if not path.is_symlink():
                return regular(guest_name.lstrip('/'))
            for parent in path.parents:
                if parent == root:
                    break
                if parent.is_symlink():
                    raise IdentityError('Unsafe release parent')
            link = os.readlink(path)
            guest_name = posixpath.normpath(link if link.startswith('/') else posixpath.join(posixpath.dirname(guest_name), link))
        raise IdentityError('Release symlink loop')
    def fields(contents):
        values = {}
        for line in contents.splitlines():
            if not line or line.startswith('#'):
                continue
            match = re.fullmatch(r'([A-Z][A-Z0-9_]*)=(.*)', line)
            if not match or match[1] in values or '$' in match[2] or '`' in match[2]:
                raise IdentityError('Invalid retained os-release field')
            try:
                parsed = shlex.split(match[2])
            except ValueError as exc:
                raise IdentityError('Invalid retained os-release quoting') from exc
            if len(parsed) != 1:
                raise IdentityError('Invalid retained os-release value')
            values[match[1]] = parsed[0]
        return values

    binary('usr/lib/xodus/xodus-welcome')
    binary('usr/lib/xodus/xodus-settings')
    for target, source in ASSET_FILES.items():
        try:
            expected = (repo / source).read_bytes()
        except OSError as exc:
            raise IdentityError('Missing graphical reference source: ' + source) from exc
        if not expected.startswith(b'\x89PNG\r\n\x1a\n'):
            raise IdentityError('Graphical reference is not PNG: ' + source)
        exact(target, expected)
    for target, source in TEXT_FILES.items():
        # apply-shell-identity writes read_text() as UTF-8, normalizing source
        # checkout line endings. Compare those exact generated bytes.
        try:
            expected = (repo / source).read_text(encoding='utf-8').encode('utf-8')
        except OSError as exc:
            raise IdentityError('Missing graphical reference source: ' + source) from exc
        exact(target, expected)

    for target, arguments in (('usr/bin/systemsettings1', ''), ('usr/bin/system-overview', '--about ')):
        exact(target, ('#!/bin/sh\nexec /usr/lib/xodus/xodus-settings ' + arguments + '"$@"\n').encode(), 0o755)
    exact('usr/share/applications/pearos-systemsettings.desktop', SETTINGS_LAUNCHER.encode())
    duplicate_launcher = root / 'usr/share/applications/xodus-settings.desktop'
    if duplicate_launcher.exists() or duplicate_launcher.is_symlink():
        raise IdentityError('Duplicate Settings desktop identity')
    lock_source = repo / 'overlay/identity/settings/source.lock.json'
    try:
        lock = json.loads(lock_source.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityError('Missing or invalid Settings source lock') from exc
    exact('usr/lib/xodus/settings-source.json', (json.dumps(lock, indent=2) + '\n').encode())
    notice = text('usr/share/licenses/xodus-settings/NOTICE')
    for line in ('Source: ' + lock['repository'], 'Commit: ' + lock['commit'],
                 'Upstream author and maintainer: Alexandru Balan, Pear Software.'):
        line_count('Settings NOTICE', notice, line)
    license_text = text('usr/share/licenses/xodus-settings/upstream-license.txt')
    if license_text.strip() != 'This program is under : GNU Public Licence V3 or newer':
        raise IdentityError('Settings upstream source license differs')

    release_source = repo / 'overlay/identity/settings/release-source.lock.json'
    release_lock = json.loads(release_source.read_text())
    exact('usr/lib/xodus/release-source.json', (json.dumps(release_lock, indent=2) + '\n').encode())
    baseline = fields((repo / 'overlay/identity/settings/upstream-os-release').read_text())
    original = fields(text('usr/lib/xodus/upstream-os-release'))
    if original.keys() != baseline.keys() or any(original[key] != value for key, value in baseline.items() if key not in ('IMAGE_ID', 'IMAGE_VERSION')):
        raise IdentityError('Retained base release provenance differs from audited source')
    if original['IMAGE_ID'] not in ('pearos-nicec0re', 'Xodus', 'Xodus-reference') or not re.fullmatch(r'(?:' + re.escape(baseline['IMAGE_VERSION']) + r'|[0-9]{4}\.(?:0[1-9]|1[0-2]))', original['IMAGE_VERSION']):
        raise IdentityError('Retained image release provenance differs')
    separate_release = root / 'usr/lib/xodus/upstream-etc-os-release'
    if separate_release.exists() or separate_release.is_symlink():
        if fields(text('usr/lib/xodus/upstream-etc-os-release')) != original:
            raise IdentityError('Retained original os-release files disagree')
    project = 'https://github.com/chewtoo22-rgb/Xodus'
    final = dict(original)
    final.update({'NAME': 'Xodus', 'PRETTY_NAME': 'Xodus', 'ID': 'xodus', 'ID_LIKE': 'arch',
                  'LOGO': 'xodus-app-icon', 'ANSI_COLOR': '38;2;173;133;245',
                  'HOME_URL': project, 'DOCUMENTATION_URL': project + '/tree/main/docs',
                  'SUPPORT_URL': project + '/issues', 'BUG_REPORT_URL': project + '/issues',
                  'IMAGE_ID': 'xodus'})
    release_bytes = ''.join(key + '=' + json.dumps(value) + '\n' for key, value in final.items()).encode()
    for relative in ('usr/lib/os-release', 'etc/os-release'):
        path = release_file(relative)
        if path.read_bytes() != release_bytes:
            raise IdentityError('Retained Xodus release identity differs: ' + relative)

    exact('usr/share/applications/xodus-welcome.desktop', WELCOME_LAUNCHER.encode())
    for home in ('etc/skel', 'home/liveuser'):
        exact(home + '/.config/autostart/xodus-welcome.desktop',
              (WELCOME_LAUNCHER + 'OnlyShowIn=KDE;\nX-KDE-autostart-phase=2\n').encode())
        for directory in ('usr/share/applications', home + '/.config/autostart'):
            exact(directory + '/welcome.desktop', b'[Desktop Entry]\nHidden=true\n')
        config = home + '/.config/'
        for name in ('plasma-org.kde.plasma.desktop-appletsrc',
                     'plasma-org.kde.plasma.desktop-appletsrc.bak'):
            relative = config + name
            contents = text(relative)
            line_count(relative, contents, 'Image=file://' + WALLPAPER, 2)
            line_count(relative, contents, 'PreviewImage=' + WALLPAPER)
            line_count(relative, contents, 'noActivityText=Xodus\\s')
            for selection in ('widgetButtonsIconsTheme=Breeze', 'widgetButtonsAuroraeTheme=',
                              'widgetElements=windowMinimizeButton,windowMaximizeButton,windowCloseButton',
                              'windowTitleUndefined=Xodus'):
                line_count(relative, contents, selection)
            if re.search(r'(?:Image|PreviewImage)=.*(?:pearOS|dark-mode\.jpg)', contents):
                raise IdentityError('Residual desktop wallpaper: ' + relative)
            inventory = [line.split('=', 1)[1] for line in contents.splitlines() if line.startswith('panelWidgets=')]
            if len(inventory) != 1:
                raise IdentityError('Missing desktop panel inventory: ' + relative)
            try:
                widgets = json.loads(inventory[0])
            except json.JSONDecodeError as exc:
                raise IdentityError('Invalid desktop panel inventory: ' + relative) from exc
            titles = {'xyz.pearos.pearmenu': 'Xodus Menu', 'PearAppTitle': 'Xodus App Title',
                      'org.kde.plasma.appmenu': 'Xodus Global Menu', 'PearPrivacy': 'Xodus Privacy',
                      'PearClock': 'Xodus Clock'}
            for name, title in titles.items():
                matches = [item for item in widgets if item.get('name') == name]
                if len(matches) != 1 or matches[0].get('title') != title:
                    raise IdentityError('Desktop widget identity differs: ' + relative + ': ' + name)
                if name == 'xyz.pearos.pearmenu' and matches[0].get('icon') != 'file:///usr/share/pixmaps/xodus-app-icon.png':
                    raise IdentityError('Desktop menu icon differs: ' + relative)
        relative = config + 'kscreenlockerrc'
        contents = text(relative)
        line_count(relative, contents, 'Image=' + WALLPAPER)
        line_count(relative, contents, 'PreviewImage=' + WALLPAPER)
        if re.search(r'(?:Image|PreviewImage)=.*(?:pearOS|dark-mode\.jpg)', contents):
            raise IdentityError('Residual lock wallpaper: ' + relative)
        relative = config + 'kdeglobals'
        contents = text(relative)
        for line in ('ColorScheme=Xodus', 'AccentColor=173,133,245',
                     'LastUsedCustomAccentColor=173,133,245'):
            line_count(relative, contents, line)
        relative = config + 'ksplashrc'
        line_count(relative, text(relative), 'Theme=pearOS')

    selection = 'etc/sddm.conf.d/20-xodus-theme.conf'
    exact(selection, b'[Theme]\nCurrent=Xodus\n')
    configurations = [root / 'etc/sddm.conf', *(root / 'etc/sddm.conf.d').glob('*.conf')]
    for path in configurations:
        if path.exists() or path.is_symlink():
            relative = str(path.relative_to(root))
            contents = text(relative)
            for value in re.findall(r'^\s*Current\s*=\s*(.*?)\s*$', contents, re.M):
                if relative != selection or value != 'Xodus':
                    raise IdentityError('Competing SDDM theme selection: ' + relative)
    for variant, expected_name in (('pearOS', 'Xodus Session Light'), ('pearOS-dark', 'Xodus Session Dark')):
        relative = 'usr/share/plasma/look-and-feel/' + variant + '/metadata.json'
        try:
            document = json.loads(text(relative))
        except json.JSONDecodeError as exc:
            raise IdentityError('Invalid session splash metadata: ' + relative) from exc
        if document.get('KPlugin', {}).get('Name') != expected_name:
            raise IdentityError('Session splash identity differs: ' + relative)
        if document['KPlugin'].get('Description') != 'Xodus Plasma session splash':
            raise IdentityError('Session splash description differs: ' + relative)

    for name, module in component_helpers(repo).items():
        try:
            result = module.verify(root, repo / 'overlay/identity' / name)
        except (SystemExit, ValueError, OSError, KeyError) as exc:
            raise IdentityError('Retained ' + name + ' identity differs: ' + str(exc)) from exc
        paths = set(module.TRANSFER_FILES)
        if name == 'desktop':
            paths.update(result)
        for relative in getattr(module, 'USER_CONFIGS', ()):
            if relative.startswith('.'):
                paths.update(home + '/' + relative for home in ('etc/skel', 'home/liveuser'))
            else:
                paths.add(relative)
        for relative in sorted(paths):
            regular(relative)

    # Hash actual retained bytes for the evidence report. This attests to the
    # inspected payload, separately from the source assertions above.
    return {'schema_version': 1, 'graphical_identity': 'pass', 'files': {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(set(checked))}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='?')
    parser.add_argument('--repo-root', '--repo', dest='repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--list-extract-paths', action='store_true')
    parser.add_argument('--list-reference-files', action='store_true')
    args = parser.parse_args()
    if args.list_extract_paths or args.list_reference_files:
        print('\n'.join(EXTRACTION_PATHS if args.list_extract_paths else REFERENCE_FILES))
        return 0
    if args.root is None:
        parser.error('root is required for graphical verification')
    try:
        result = verify(args.root, args.repo)
    except (IdentityError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print('Graphical identity verification failed: ' + str(exc), file=sys.stderr)
        return 1
    serialized = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(serialized, encoding='utf-8', newline='\n')
    print('Verified Xodus graphical payload (' + str(len(result['files'])) + ' files)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

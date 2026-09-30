#!/usr/bin/env python3
"""Capture reviewed live identity bytes and transfer them into a fresh target.

No partitions, mounts, accounts, drivers, services or bootloader commands are
created by this helper. Installer hooks run the existing boot configuration
commands after the boot files have been staged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

MANIFEST = 'usr/lib/xodus/identity-payload.json'
SKEL = (
    '.config/kscreenlockerrc', '.config/kdeglobals', '.config/ksplashrc',
    '.config/plasma-org.kde.plasma.desktop-appletsrc',
    '.config/plasma-org.kde.plasma.desktop-appletsrc.bak',
    '.config/filer-topbar-appletsrc', '.config/autostart/pearos-notch.desktop',
    '.config/autostart/welcome.desktop', '.config/autostart/xodus-welcome.desktop',
)
FIXED = [
    'usr/share/wallpapers/Xodus/xodus-wallpaper.png',
    'usr/share/pixmaps/xodus-app-icon.png',
    'usr/lib/xodus/xodus-welcome', 'usr/lib/xodus/xodus-settings',
    'usr/lib/xodus/xodus-restore-user-identity', 'usr/lib/xodus/xodus-identity-payload',
    'usr/lib/xodus/settings-source.json', 'usr/lib/xodus/release-source.json',
    'usr/lib/xodus/upstream-os-release', 'usr/lib/os-release', 'etc/arch-release',
    'usr/bin/systemsettings1', 'usr/bin/system-overview',
    'usr/share/applications/welcome.desktop',
    'usr/share/applications/xodus-welcome.desktop',
    'usr/share/applications/pearos-systemsettings.desktop',
    'usr/share/applications/pearos-notch.desktop',
    'usr/share/licenses/xodus-shell/LICENSE',
    'usr/share/licenses/xodus-settings/NOTICE',
    'usr/share/licenses/xodus-settings/upstream-license.txt',
    'usr/share/color-schemes/Xodus.colors',
    'etc/sddm.conf.d/20-xodus-theme.conf',
    'usr/share/sounds/pearOS-sounds/index.theme',
    'usr/share/plasma/plasmoids/xyz.pearos.pearmenu/metadata.json',
    'usr/share/plasma/plasmoids/xyz.pearos.pearmenu/contents/config/main.xml',
    'usr/share/plasma/plasmoids/xyz.pearos.pearmenu/contents/ui/MainMenuButton.qml',
    'usr/share/plasma/plasmoids/PearDock/contents/ui/integrations/PearFinder.qml',
    'usr/share/plasma/plasmoids/PearDock/contents/ui/integrations/PearLauncher.qml',
    'usr/share/plasma/plasmoids/PearAppTitle/contents/config/main.xml',
    'usr/share/plasma/plasmoids/PearAppTitle/contents/ui/config/ConfigAppearance.qml',
    'usr/share/plasma/plasmoids/PearLauncher/contents/config/main.xml',
    'usr/share/plasma/plasmoids/PearLauncher/contents/ui/main.qml',
]
for widget in ('PearAppTitle', 'PearClock', 'PearCalendar', 'PearControlCentre',
               'PearFinder', 'PearFolderArc', 'PearLauncher', 'PearPrivacy',
               'PearTaskManager', 'PearTrash', 'PearWeather', 'PearDock'):
    FIXED.append(f'usr/share/plasma/plasmoids/{widget}/metadata.json')
for variant in ('pearOS', 'pearOS-dark'):
    for name in ('Main.qml', 'theme.conf', 'theme.conf.user', 'metadata.desktop'):
        FIXED.append(f'usr/share/sddm/themes/{variant}/{name}')
    for name in ('metadata.json', 'contents/splash/Splash.qml'):
        FIXED.append(f'usr/share/plasma/look-and-feel/{variant}/{name}')
    for name in ('metadata.json', 'metadata.desktop'):
        FIXED.append(f'usr/share/plasma/desktoptheme/{variant}/{name}')
    FIXED += [f'usr/share/color-schemes/{variant}.colors',
              f'usr/share/aurorae/themes/{variant}/metadata.desktop']
for name in ('Main.qml', 'metadata.desktop', 'theme.conf', 'LICENSE'):
    FIXED.append(f'usr/share/sddm/themes/Xodus/{name}')
FIXED += ['etc/skel/' + relative for relative in SKEL]
BOOT_TREES = ('usr/share/plymouth/themes/xodus', 'usr/share/grub/themes/Xodus')
BOOT_REQUIRED = {
    'usr/share/plymouth/themes/xodus/xodus.plymouth',
    'usr/share/plymouth/themes/xodus/xodus.script',
    'usr/share/grub/themes/Xodus/theme.txt',
    'usr/share/grub/themes/Xodus/background.png',
    *(f'usr/share/plymouth/themes/xodus/frame-{index:03d}.png' for index in range(241)),
    *(f'usr/share/grub/themes/Xodus/{name}.pf2' for name in (
        'Poppins-14', 'Poppins-16', 'Poppins-18', 'Poppins-20', 'Poppins-48',
        'terminus-12', 'terminus-14', 'terminus-16')),
}
OPTIONAL = ('usr/lib/xodus/upstream-etc-os-release',)
SHA = re.compile(r'^[0-9a-f]{40}$')


def fail(message):
    raise ValueError('Xodus installed identity: ' + message)


def safe(root: Path, relative: str, required=False):
    path_parts = Path(relative).parts
    if not relative or relative.startswith('/') or '..' in path_parts or '.' in path_parts:
        fail('unsafe relative path: ' + relative)
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            fail('symlink in identity path: ' + relative)
        if candidate != path and candidate.exists() and not candidate.is_dir():
            fail('non-directory identity parent: ' + relative)
    if root not in path.resolve().parents:
        fail('identity path escapes root: ' + relative)
    if path.exists() and not path.is_file():
        fail('identity destination is not regular: ' + relative)
    if path.is_file() and path.stat().st_nlink != 1:
        fail('hardlink in identity path: ' + relative)
    if required and not path.is_file():
        fail('missing identity file: ' + relative)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_commit(root):
    text = safe(root, 'usr/lib/xodus/build-info', True).read_text()
    values = re.findall(r'^XODUS_SOURCE_COMMIT=([0-9a-f]{40})$', text, re.M)
    if len(values) != 1:
        fail('live image lacks one exact Xodus source commit')
    return values[0]


def inventory(root):
    # The package may include many other files. Only this closed inventory is
    # transferred; an extra executable or arbitrary theme file is never admitted.
    files = set(FIXED) | BOOT_REQUIRED
    for relative in BOOT_TREES:
        directory = root / relative
        if directory.is_symlink() or not directory.is_dir():
            fail('missing or unsafe boot theme tree: ' + relative)
    files.update(relative for relative in OPTIONAL if safe(root, relative).exists())
    return sorted(files)


def file_mode(relative):
    return '0755' if relative.startswith('usr/bin/') or relative in (
        'usr/lib/xodus/xodus-welcome', 'usr/lib/xodus/xodus-settings',
        'usr/lib/xodus/xodus-restore-user-identity', 'usr/lib/xodus/xodus-identity-payload') else '0644'


def verify_brand(root):
    for name in ('xodus-welcome', 'xodus-settings'):
        path = safe(root, 'usr/lib/xodus/' + name, True)
        if path.read_bytes()[:4] != b'\x7fELF' or not os.access(path, os.X_OK):
            fail('missing executable compiled app: ' + name)
    checks = {
        'usr/share/applications/xodus-welcome.desktop': 'Name=Xodus Welcome',
        'usr/share/applications/pearos-systemsettings.desktop': 'Name=Xodus Settings',
        'etc/sddm.conf.d/20-xodus-theme.conf': 'Current=Xodus',
        'etc/skel/.config/kdeglobals': 'ColorScheme=Xodus',
        'usr/share/color-schemes/Xodus.colors': 'Name=Xodus',
        'usr/share/grub/themes/Xodus/theme.txt': 'Xodus',
        'usr/share/plymouth/themes/xodus/xodus.plymouth': 'Name=Xodus',
        'usr/lib/os-release': 'ID=xodus',
    }
    for relative, marker in checks.items():
        if marker not in safe(root, relative, True).read_text():
            fail('live identity is not applied: ' + relative)


def capture(root):
    if root.is_symlink() or not root.is_dir():
        fail('capture requires a real staged live root')
    root = root.resolve(strict=True)
    if root == Path('/'):
        fail('capture requires a staged live root')
    commit = source_commit(root)
    files = inventory(root)
    verify_brand(root)
    entries = []
    for relative in files:
        path = safe(root, relative, True)
        mode = file_mode(relative)
        if mode == '0755' and not os.access(path, os.X_OK):
            fail('required executable mode is missing: ' + relative)
        entries.append({'path': relative, 'sha256': digest(path),
                        'mode': mode})
    manifest = {'schema': 1, 'source_commit': commit, 'files': entries}
    output = safe(root, MANIFEST)
    if output.exists():
        fail('live identity manifest already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    return manifest


def read_manifest(source, expected_source):
    if not SHA.fullmatch(expected_source) or source_commit(source) != expected_source:
        fail('live image source does not match the qualified installer')
    document = json.loads(safe(source, MANIFEST, True).read_text())
    if set(document) != {'schema', 'source_commit', 'files'} or document['schema'] != 1:
        fail('invalid identity manifest schema')
    if document['source_commit'] != expected_source:
        fail('identity manifest source does not match the qualified installer')
    files = document['files']
    if not isinstance(files, list) or not files:
        fail('empty identity manifest')
    paths = []
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {'path', 'sha256', 'mode'}:
            fail('invalid identity manifest entry')
        relative = entry['path']
        if not isinstance(relative, str) or relative not in set(FIXED) | BOOT_REQUIRED | set(OPTIONAL):
            fail('identity manifest attempts an unreviewed path')
        paths.append(relative)
        if entry['mode'] != file_mode(relative) or not isinstance(entry['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
            fail('invalid identity hash or mode')
        if digest(safe(source, relative, True)) != entry['sha256']:
            fail('live identity payload hash changed: ' + relative)
    if paths != sorted(set(paths)) or set(paths) != set(inventory(source)):
        fail('identity manifest file inventory changed')
    verify_brand(source)
    return document


def grub_defaults(target):
    path = safe(target, 'etc/default/grub', True)
    lines = path.read_text().splitlines()
    for key, value in (('GRUB_THEME', '"/usr/share/grub/themes/Xodus/theme.txt"'),
                       ('GRUB_DISTRIBUTOR', '"Xodus"')):
        positions = [i for i, line in enumerate(lines) if re.match(r'^\s*' + key + r'\s*=', line)]
        if len(positions) > 1:
            fail('duplicate installed GRUB setting: ' + key)
        if positions:
            lines[positions[0]] = key + '=' + value
        else:
            lines.append(key + '=' + value)
    return path, '\n'.join(lines) + '\n'


def initramfs_hooks(target):
    path = safe(target, 'etc/mkinitcpio.conf', True)
    text = path.read_text()
    matches = list(re.finditer(r'^HOOKS=\(([^\n]*)\)$', text, re.M))
    if len(matches) != 1:
        fail('installed initramfs must contain one reviewed HOOKS array')
    match = matches[0]
    hooks = match.group(1).split()
    if not hooks or any(not re.fullmatch(r'[a-zA-Z0-9_-]+', hook) for hook in hooks):
        fail('unreviewed installed initramfs hook syntax')
    if 'systemd' in hooks or 'sd-plymouth' in hooks:
        fail('installed systemd initramfs requires a separately reviewed Plymouth hook')
    if 'plymouth' not in hooks:
        # Keep all target hooks in their existing order. Plymouth runs after
        # display setup and before any encrypt/password prompt hook.
        position = hooks.index('kms') + 1 if 'kms' in hooks else hooks.index('udev') + 1 if 'udev' in hooks else 1
        hooks.insert(position, 'plymouth')
    if hooks.count('plymouth') != 1:
        fail('duplicate installed Plymouth hook')
    return path, text[:match.start()] + 'HOOKS=(' + ' '.join(hooks) + ')' + text[match.end():]


def release_link(target):
    path = target / 'etc/os-release'
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir() or target not in parent.resolve().parents:
        fail('unsafe installed OS release parent')
    if path.is_symlink():
        if os.readlink(path) not in ('../usr/lib/os-release', '/usr/lib/os-release'):
            fail('unreviewed installed OS release symlink')
        return path, 'link'
    if path.exists() and not path.is_file():
        fail('invalid installed OS release file')
    return path, 'regular' if path.exists() else 'new-link'


def user_homes(target):
    accounts = safe(target, 'etc/passwd', True).read_text().splitlines()
    result = []
    for row in accounts:
        fields = row.split(':')
        if len(fields) != 7:
            fail('invalid target account record')
        uid, gid = int(fields[2]), int(fields[3])
        home = fields[5]
        if not 1000 <= uid < 60000 or not home.startswith('/home/'):
            continue
        relative = home.lstrip('/')
        directory = target / relative
        if directory.is_symlink() or not directory.is_dir() or target not in directory.resolve().parents:
            fail('unsafe target user home: ' + home)
        result.append((relative, uid, gid))
    return result


def target_boundary(source, target):
    if target == Path('/') or source == target:
        fail('target must be a separate installation root')
    if source == Path('/'):
        # The pinned setup mounts its selected target at exactly /mnt. Source
        # paths come only from the closed /usr and /etc graphical allowlist.
        if target != Path('/mnt'):
            fail('real live source may transfer only into the pinned /mnt target')
    elif source in target.parents or target in source.parents:
        fail('fixture target must be independent of the staged live source')


def sddm_selections(target):
    directory = target / 'etc/sddm.conf.d'
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        fail('unsafe installed SDDM configuration directory')
    updates = []
    paths = [target / 'etc/sddm.conf', *directory.glob('*.conf')]
    for path in paths:
        relative = path.relative_to(target).as_posix()
        if relative == 'etc/sddm.conf.d/20-xodus-theme.conf':
            continue  # The full transfer replaces this reviewed selection.
        if not path.exists() and not path.is_symlink():
            continue
        path = safe(target, relative, True)
        section = None
        output = []
        for line in path.read_text().splitlines(keepends=True):
            heading = re.fullmatch(r'\s*\[([^]\n]+)\]\s*', line.strip())
            if heading:
                section = heading.group(1)
            if re.match(r'^\s*Current\s*=', line):
                if section != 'Theme':
                    fail('unreviewed installed SDDM Current setting: ' + relative)
                continue
            output.append(line)
        contents = ''.join(output).encode()
        if contents != path.read_bytes():
            updates.append((path, contents, stat.S_IMODE(path.stat().st_mode), None))
    return updates


def runtime_check(target):
    for name, libs, style, arguments in (
        ('xodus-welcome', ('libQt5Widgets.so.5', 'libQt5Gui.so.5', 'libQt5Core.so.5'),
         'QT_STYLE_OVERRIDE=Fusion', ['--self-test']),
        ('xodus-settings', ('libQt6Core.so.6', 'libQt6Gui.so.6', 'libQt6Quick.so.6', 'libQt6Qml.so.6'),
         'QT_QUICK_CONTROLS_STYLE=Basic', ['--self-test', '--about']),
    ):
        binary = '/usr/lib/xodus/' + name
        result = subprocess.run(['arch-chroot', str(target), '/usr/bin/ldd', binary],
                                capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        if result.returncode or 'not found' in output or any(lib not in output for lib in libs):
            fail('installed app ABI check failed: ' + name)
        result = subprocess.run(['arch-chroot', str(target), '/usr/bin/env',
                                 'LD_BIND_NOW=1', 'QT_QPA_PLATFORM=offscreen',
                                 'QT_QUICK_BACKEND=software', style, binary, *arguments],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            fail('installed app render check failed: ' + name)


def install(source, target, expected_source, phase='full'):
    if source.is_symlink() or target.is_symlink() or not source.is_dir() or not target.is_dir():
        fail('source and target must be real directories')
    source, target = source.resolve(strict=True), target.resolve(strict=True)
    target_boundary(source, target)
    document = read_manifest(source, expected_source)
    entries = [entry for entry in document['files'] if phase == 'full' or any(
        entry['path'].startswith(prefix + '/') for prefix in BOOT_TREES)]
    updates = [(safe(target, entry['path']), safe(source, entry['path'], True).read_bytes(),
                int(entry['mode'], 8), None) for entry in entries]
    grub, contents = grub_defaults(target)
    updates.append((grub, contents.encode(), 0o644, None))
    if phase == 'boot':
        hooks, contents = initramfs_hooks(target)
        updates.append((hooks, contents.encode(), 0o644, None))
    release = None
    if phase == 'full':
        updates.extend(sddm_selections(target))
        release, release_kind = release_link(target)
        if release_kind == 'regular':
            updates.append((release, safe(source, 'usr/lib/os-release', True).read_bytes(), 0o644, None))
        for home, uid, gid in user_homes(target):
            for relative in SKEL:
                updates.append((safe(target, home + '/' + relative),
                                safe(source, 'etc/skel/' + relative, True).read_bytes(),
                                0o644, (uid, gid)))
    # All source checks and destination path checks finish before transfer.
    # ABI checks necessarily follow staging, and abort the installer on failure.
    for path, contents, mode, ownership in updates:
        missing = []
        parent = path.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        path.parent.mkdir(parents=True, exist_ok=True)
        if ownership:
            for parent in missing:
                os.chown(parent, *ownership)
        path.write_bytes(contents)
        path.chmod(mode)
        if ownership:
            os.chown(path, *ownership)
    if phase == 'full':
        if release_kind == 'new-link':
            release.symlink_to('../usr/lib/os-release')
        runtime_check(target)
        receipt = safe(target, 'usr/lib/xodus/installed-identity.json')
        receipt.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Installed Xodus identity phase={phase} files={len(updates)} source={expected_source}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    cap = subparsers.add_parser('capture')
    cap.add_argument('root', type=Path)
    transfer = subparsers.add_parser('install')
    transfer.add_argument('--source-root', type=Path, default=Path('/'))
    transfer.add_argument('--target-root', type=Path, required=True)
    transfer.add_argument('--expected-source', required=True)
    transfer.add_argument('--phase', choices=('boot', 'full'), default='full')
    verify = subparsers.add_parser('verify')
    verify.add_argument('--source-root', type=Path, default=Path('/'))
    verify.add_argument('--expected-source', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'capture':
            manifest = capture(args.root)
            print(f'Captured Xodus identity source={manifest["source_commit"]} files={len(manifest["files"])}')
        elif args.command == 'install':
            install(args.source_root, args.target_root, args.expected_source, args.phase)
        else:
            read_manifest(args.source_root.resolve(strict=True), args.expected_source)
            print('Verified qualified Xodus graphical identity payload')
    except (ValueError, OSError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc))

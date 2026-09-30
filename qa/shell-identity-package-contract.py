#!/usr/bin/env python3
"""Exercise the shell overlay against real, versioned package archives.

Run on Linux with Python 3.14 (tarfile's zstd support). Supply the original
pearos-settings, pearos-dock and pearos-notch archives as positional arguments.
Only fixture text is extracted; no package binary or script is executed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('packages', nargs=3, type=Path)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
helper = repo / 'overlay/identity/apply-shell-identity.sh'
versions = {'pearos-settings': '26.7.0-4', 'pearos-dock': '26.6.10-5',
            'pearos-notch': '26.6.1-1'}


def snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


def apply(root, success):
    result = subprocess.run(['bash', str(helper), str(root)],
                            capture_output=True, text=True)
    assert (result.returncode == 0) == success, result.stderr
    return result


with tempfile.TemporaryDirectory(prefix='xodus-shell-contract-') as temporary:
    base = Path(temporary)
    original = base / 'original'
    seen = set()
    for package in args.packages:
        with tarfile.open(package) as archive:
            info = dict(line.split(' = ', 1) for line in
                        archive.extractfile('.PKGINFO').read().decode().splitlines()
                        if line.startswith(('pkgname = ', 'pkgver = ')))
            assert versions.get(info['pkgname']) == info['pkgver'], info
            assert info['pkgname'] not in seen
            seen.add(info['pkgname'])
            for member in archive:
                if not member.isfile():
                    continue
                relative = Path(member.name)
                included = member.name.startswith((
                    'etc/skel/.config/', 'usr/share/plasma/',
                    'usr/share/sddm/themes/', 'usr/share/color-schemes/',
                    'usr/share/aurorae/themes/', 'usr/share/sounds/pearOS-sounds/'))
                included |= member.name == 'usr/share/applications/pearos-notch.desktop'
                if not included or relative.suffix.lower() in (
                        '.png', '.jpg', '.jpeg', '.otf', '.ttf', '.svg', '.so', '.gif'):
                    continue
                target = original / relative
                assert original.resolve() in target.resolve().parents
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
        print(f'{info["pkgname"]} {info["pkgver"]} sha256={hashlib.sha256(package.read_bytes()).hexdigest()}')
    assert seen == versions.keys()
    shutil.copytree(original / 'etc/skel', original / 'home/liveuser')
    sddm = original / 'etc/sddm.conf.d'
    sddm.mkdir(parents=True)
    autologin = '[Autologin]\nRelogin=true\nSession=plasma\nUser=liveuser\n'
    (sddm / 'autologin.conf').write_text(autologin)
    for source_name, destination in (
        ('xodus-wallpaper.png', 'usr/share/wallpapers/Xodus/xodus-wallpaper.png'),
        ('xodus-app-icon.png', 'usr/share/pixmaps/xodus-app-icon.png'),
    ):
        target = original / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / 'overlay/identity/assets' / source_name, target)

    # A drift late in validation must leave all earlier files untouched.
    bad = base / 'bad'
    shutil.copytree(original, bad)
    dock = bad / 'usr/share/plasma/plasmoids/PearDock/metadata.json'
    dock.write_text('{}')
    before = snapshot(bad)
    result = apply(bad, False)
    assert 'invalid Plasma metadata' in result.stderr, result.stderr
    assert snapshot(bad) == before

    localized = base / 'localized'
    shutil.copytree(original, localized)
    dock = localized / 'usr/share/plasma/plasmoids/PearDock/metadata.json'
    document = json.loads(dock.read_text())
    document['KPlugin']['Name[es]'] = 'Pear Dock'
    dock.write_text(json.dumps(document))
    before = snapshot(localized)
    result = apply(localized, False)
    assert 'unreviewed localized Plasma branding' in result.stderr
    assert snapshot(localized) == before

    conflict = base / 'conflict'
    shutil.copytree(original, conflict)
    (conflict / 'etc/sddm.conf.d/99-other.conf').write_text('[Theme]\nCurrent=other\n')
    before = snapshot(conflict)
    result = apply(conflict, False)
    assert 'unreviewed SDDM theme selection' in result.stderr
    assert snapshot(conflict) == before

    good = base / 'good'
    shutil.copytree(original, good)
    result = apply(good, True)
    assert (good / 'etc/sddm.conf.d/autologin.conf').read_text() == autologin
    assert (good / 'etc/sddm.conf.d/20-xodus-theme.conf').read_text() == '[Theme]\nCurrent=Xodus\n'
    for home in ('etc/skel', 'home/liveuser'):
        lock = (good / home / '.config/kscreenlockerrc').read_text()
        assert lock.count('/usr/share/wallpapers/Xodus/xodus-wallpaper.png') == 2
        globals_text = (good / home / '.config/kdeglobals').read_text()
        assert 'AccentColor=173,133,245' in globals_text
        assert 'ColorScheme=Xodus' in globals_text
        assert 'Mutern' not in globals_text
        panel = (good / home / '.config/plasma-org.kde.plasma.desktop-appletsrc').read_text()
        assert '"title":"Pear' not in panel
        assert '"title":"pearOS' not in panel
        assert 'noActivityText=Xodus\\s' in panel
    menu = good / 'usr/share/plasma/plasmoids/xyz.pearos.pearmenu'
    assert 'About Xodus' in (menu / 'contents/ui/MainMenuButton.qml').read_text()
    assert 'systemsettings1' in (menu / 'contents/config/main.xml').read_text()
    assert 'system-overview' in (menu / 'contents/config/main.xml').read_text()
    launcher = (good / 'usr/share/plasma/plasmoids/PearDock/contents/ui/integrations/PearLauncher.qml').read_text()
    assert 'source: "file:///usr/share/pixmaps/xodus-app-icon.png"' in launcher
    assert json.loads((menu / 'metadata.json').read_text())['KPlugin']['Name'] == 'Xodus Menu'
    for variant in ('pearOS', 'pearOS-dark'):
        splash = (good / f'usr/share/plasma/look-and-feel/{variant}/contents/splash/Splash.qml').read_text()
        assert 'Preparing your desktop' in splash
        assert 'target: bottomRect' not in splash
    assert 'SPDX-License-Identifier: MIT' in (good / 'usr/share/sddm/themes/Xodus/Main.qml').read_text()
    assert (good / 'usr/share/licenses/xodus-shell/LICENSE').is_file()
    assert 'Name=Xodus' in (good / 'usr/share/color-schemes/Xodus.colors').read_text()
    print(result.stdout.strip())
    print('Shell package contract: PASS (real archives, drift, localization, conflict, output)')

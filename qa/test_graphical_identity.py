#!/usr/bin/env python3
"""Retained-image identity must reject missing, altered and unsafe payloads."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from graphical_component_fixture import populate

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('graphical_identity', REPO / 'qa/verify-graphical-identity.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
spec2 = importlib.util.spec_from_file_location('settings_identity', REPO / 'overlay/identity/settings/apply-settings.py')
settings = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(settings)


class RetainedGraphicalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / 'root'
        self.reference = base / 'reference'
        self.root.mkdir()
        self.reference.mkdir()
        def source(relative, contents):
            path = self.reference / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        for target, relative in gate.ASSET_FILES.items():
            contents = b'\x89PNG\r\n\x1a\nretained image fixture:' + relative.encode()
            source(relative, contents)
            self.write(target, contents)
        for target, relative in gate.TEXT_FILES.items():
            contents = ('Source fixture: ' + relative + '\n').encode()
            source(relative, contents)
            self.write(target, contents)
        for name in ('source.lock.json', 'release-source.lock.json', 'upstream-os-release'):
            relative = 'overlay/identity/settings/' + name
            source(relative, (REPO / relative).read_bytes())
        native = bytearray(64)
        native[:7] = b'\x7fELF\x02\x01\x01'
        native[16:18] = b'\x03\x00'
        native[18:20] = b'\x3e\x00'
        for name in ('xodus-settings', 'xodus-welcome'):
            self.write('usr/lib/xodus/' + name, native, 0o755)
        for target, arguments in (('usr/bin/systemsettings1', ''), ('usr/bin/system-overview', '--about ')):
            self.write(target, ('#!/bin/sh\nexec /usr/lib/xodus/xodus-settings ' + arguments + '"$@"\n').encode(), 0o755)
        self.write('usr/share/applications/pearos-systemsettings.desktop', gate.SETTINGS_LAUNCHER.encode())
        lock = json.loads((self.reference / 'overlay/identity/settings/source.lock.json').read_text())
        self.write('usr/lib/xodus/settings-source.json', (json.dumps(lock, indent=2) + '\n').encode())
        self.write('usr/share/licenses/xodus-settings/NOTICE',
                   ('Source: ' + lock['repository'] + '\nCommit: ' + lock['commit'] + '\n'
                    'Upstream author and maintainer: Alexandru Balan, Pear Software.\n').encode())
        self.write('usr/share/licenses/xodus-settings/upstream-license.txt', b'This program is under : GNU Public Licence V3 or newer\n')
        self.write('usr/share/applications/xodus-welcome.desktop', gate.WELCOME_LAUNCHER.encode())
        widgets = [{'name': name, 'title': title} for name, title in (
            ('xyz.pearos.pearmenu', 'Xodus Menu'), ('PearAppTitle', 'Xodus App Title'),
            ('org.kde.plasma.appmenu', 'Xodus Global Menu'), ('PearPrivacy', 'Xodus Privacy'), ('PearClock', 'Xodus Clock'))]
        widgets[0]['icon'] = 'file:///usr/share/pixmaps/xodus-app-icon.png'
        for home in ('etc/skel', 'home/liveuser'):
            self.write(home + '/.config/autostart/xodus-welcome.desktop', (gate.WELCOME_LAUNCHER + 'OnlyShowIn=KDE;\nX-KDE-autostart-phase=2\n').encode())
            for directory in ('usr/share/applications', home + '/.config/autostart'):
                self.write(directory + '/welcome.desktop', b'[Desktop Entry]\nHidden=true\n')
            config = home + '/.config/'
            desktop = ('Image=file://' + gate.WALLPAPER + '\n') * 2 + 'PreviewImage=' + gate.WALLPAPER + '\nnoActivityText=Xodus\\s\npanelWidgets=' + json.dumps(widgets) + '\n'
            desktop += ('widgetButtonsIconsTheme=Breeze\nwidgetButtonsAuroraeTheme=\n'
                        'widgetElements=windowMinimizeButton,windowMaximizeButton,windowCloseButton\n'
                        'windowTitleUndefined=Xodus\n')
            for name in ('plasma-org.kde.plasma.desktop-appletsrc', 'plasma-org.kde.plasma.desktop-appletsrc.bak'):
                self.write(config + name, desktop.encode())
            self.write(config + 'kscreenlockerrc', ('Image=' + gate.WALLPAPER + '\nPreviewImage=' + gate.WALLPAPER + '\n').encode())
            self.write(config + 'kdeglobals', b'ColorScheme=Xodus\nAccentColor=173,133,245\nLastUsedCustomAccentColor=173,133,245\n')
            self.write(config + 'ksplashrc', b'Theme=pearOS\n')
        self.write('etc/sddm.conf.d/20-xodus-theme.conf', b'[Theme]\nCurrent=Xodus\n')
        for variant, name in (('pearOS', 'Xodus Session Light'), ('pearOS-dark', 'Xodus Session Dark')):
            self.write('usr/share/plasma/look-and-feel/' + variant + '/metadata.json', json.dumps({'KPlugin': {'Name': name, 'Description': 'Xodus Plasma session splash'}}).encode())
        self.write('usr/lib/os-release', (self.reference / 'overlay/identity/settings/upstream-os-release').read_bytes())
        settings.apply_release_identity(self.root, self.reference / 'overlay/identity/settings')
        populate(self.root, self.reference, REPO)

    def write(self, relative, contents, mode=0o644):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        path.chmod(mode)

    def tearDown(self):
        self.temporary.cleanup()

    def verify(self):
        return gate.verify(self.root, self.reference)

    def test_bound_payload_returns_actual_hash_manifest(self):
        report = self.verify()
        self.assertEqual(report['graphical_identity'], 'pass')
        self.assertGreater(len(report['files']), 35)
        self.assertEqual(len(report['files']['usr/lib/xodus/xodus-settings']), 64)

    def test_missing_native_app_fails(self):
        (self.root / 'usr/lib/xodus/xodus-settings').unlink()
        with self.assertRaisesRegex(gate.IdentityError, 'Missing graphical'):
            self.verify()

    def test_wrong_architecture_or_nonexecuting_mode_fails(self):
        native = self.root / 'usr/lib/xodus/xodus-settings'
        native.chmod(0o644)
        with self.assertRaisesRegex(gate.IdentityError, '0755'):
            self.verify()
        native.chmod(0o755)
        contents = bytearray(native.read_bytes())
        contents[18:20] = b'\xb7\x00'
        native.write_bytes(contents)
        with self.assertRaisesRegex(gate.IdentityError, 'x86-64 ELF'):
            self.verify()

    def test_altered_source_qml_fails(self):
        path = self.root / 'usr/share/sddm/themes/Xodus/Main.qml'
        path.write_bytes(path.read_bytes() + b'// altered after source build\n')
        with self.assertRaisesRegex(gate.IdentityError, 'bytes differ'):
            self.verify()

    def test_wrong_settings_source_provenance_fails(self):
        path = self.root / 'usr/lib/xodus/settings-source.json'
        document = json.loads(path.read_text())
        document['commit'] = 'f' * 40
        path.write_text(json.dumps(document, indent=2) + '\n')
        with self.assertRaisesRegex(gate.IdentityError, 'bytes differ'):
            self.verify()

    def test_legacy_about_command_or_duplicate_settings_launcher_fails(self):
        self.write('usr/bin/system-overview', b'#!/bin/sh\nexec npm start about\n', 0o755)
        with self.assertRaisesRegex(gate.IdentityError, 'bytes differ'):
            self.verify()

    def test_competing_sddm_selection_fails(self):
        self.write('etc/sddm.conf.d/99-other.conf', b'[Theme]\nCurrent=pearOS\n')
        with self.assertRaisesRegex(gate.IdentityError, 'Competing SDDM'):
            self.verify()

    def test_wrong_lock_wallpaper_fails(self):
        self.write('home/liveuser/.config/kscreenlockerrc', b'Image=/usr/share/extras/wallpapers/Default/dark-mode.jpg\n')
        with self.assertRaisesRegex(gate.IdentityError, 'Graphical selection'):
            self.verify()

    def test_active_panel_cannot_restore_traffic_light_controls(self):
        path = self.root / 'home/liveuser/.config/plasma-org.kde.plasma.desktop-appletsrc'
        path.write_text(path.read_text().replace('widgetButtonsIconsTheme=Breeze', 'widgetButtonsIconsTheme=Aurorae'))
        with self.assertRaisesRegex(gate.IdentityError, 'Graphical selection'):
            self.verify()

    def test_release_absolute_link_stays_inside_guest(self):
        link = self.root / 'etc/os-release'
        link.unlink()
        link.symlink_to('/usr/lib/os-release')
        self.assertEqual(self.verify()['graphical_identity'], 'pass')
        link.unlink()
        link.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(gate.IdentityError, 'audited target'):
            self.verify()

    def test_altered_base_version_fails(self):
        path = self.root / 'usr/lib/os-release'
        path.write_text(path.read_text().replace('VERSION="26.10"', 'VERSION="99.0"'))
        with self.assertRaisesRegex(gate.IdentityError, 'release identity differs'):
            self.verify()

    def test_real_filename_image_provenance_is_accepted(self):
        original = self.root / 'usr/lib/xodus/upstream-os-release'
        original.write_text(original.read_text().replace('IMAGE_ID=pearos-nicec0re', 'IMAGE_ID=Xodus-reference').replace('IMAGE_VERSION=26.10', 'IMAGE_VERSION=2026.10'))
        release = self.root / 'usr/lib/os-release'
        release.write_text(release.read_text().replace('IMAGE_VERSION="26.10"', 'IMAGE_VERSION="2026.10"'))
        self.assertEqual(self.verify()['graphical_identity'], 'pass')

    def test_unreviewed_filename_image_provenance_fails(self):
        original = self.root / 'usr/lib/xodus/upstream-os-release'
        original.write_text(original.read_text().replace('IMAGE_ID=pearos-nicec0re', 'IMAGE_ID=other-image'))
        with self.assertRaisesRegex(gate.IdentityError, 'image release provenance'):
            self.verify()

    def test_forged_separate_base_provenance_fails(self):
        original = (self.root / 'usr/lib/xodus/upstream-os-release').read_text()
        self.write('usr/lib/xodus/upstream-etc-os-release', original.replace('VERSION="26.10"', 'VERSION="99.1"').encode())
        with self.assertRaisesRegex(gate.IdentityError, 'files disagree'):
            self.verify()

    def test_guest_release_link_loop_fails(self):
        release = self.root / 'usr/lib/os-release'
        release.unlink()
        release.symlink_to('/etc/os-release')
        with self.assertRaisesRegex(gate.IdentityError, 'symlink loop'):
            self.verify()

    def test_duplicate_launcher_alias_is_rejected_even_when_dangling(self):
        duplicate = self.root / 'usr/share/applications/xodus-settings.desktop'
        duplicate.symlink_to('/missing/xodus-settings.desktop')
        with self.assertRaisesRegex(gate.IdentityError, 'Duplicate Settings'):
            self.verify()


if __name__ == '__main__':
    unittest.main()

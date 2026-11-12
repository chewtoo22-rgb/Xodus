#!/usr/bin/env python3
"""Apply the reviewed Xodus Control Center frontend after the base shell hook."""
import argparse
import hashlib
import json
from pathlib import Path
import re

BASE = Path('usr/share/plasma/plasmoids/PearControlCentre')
HERE = Path(__file__).resolve().parent
RECEIPT = 'usr/share/xodus/identity/control-center.json'
_LOCK = json.loads((HERE / 'source.lock.json').read_text())
# Include the original providers/pages/assets as well as the new frontend.
TRANSFER_FILES = tuple(sorted({(BASE / name).as_posix() for name in _LOCK['files']} |
                              {(BASE / 'contents' / name).as_posix() for name in _LOCK['payload']} |
                              {RECEIPT}))
MINIMAL_REFS = ('usr/share/extras/system-settings/themeswitcher/kde-theme-switch.sh',
                'usr/share/extras/system-settings/themeswitcher/state')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def receipt(lock):
    document = {'schema': 1, 'component': 'xodus-control-center',
                'source_package': lock['package'], 'source_files': lock['files'],
                'payload': lock['payload'], 'deployed_files': lock['deployed']}
    return (json.dumps(document, sort_keys=True, indent=2) + '\n').encode()


def verify(root, payload=HERE):
    """Verify deployed bytes against the trusted reviewed derivation manifest."""
    root = Path(root).resolve(strict=True)
    lock = json.loads((Path(payload) / 'source.lock.json').read_text())
    for path in [root / BASE, *(root / BASE).parents, *(root / BASE).rglob('*')]:
        if path.is_symlink():
            raise SystemExit(f'Control Center verification found symlink: {path}')
    actual = {p.relative_to(root / BASE).as_posix(): digest(p.read_bytes())
              for p in (root / BASE).rglob('*') if p.is_file()}
    if actual != lock['deployed']:
        raise SystemExit('Control Center deployed bytes differ from reviewed derivation')
    marker = root / RECEIPT
    if marker.is_symlink() or not marker.is_file() or marker.read_bytes() != receipt(lock):
        raise SystemExit('Control Center derivation receipt differs')
    return {'files': len(actual), 'source_package': lock['package']}


def replace(text, before, after, name):
    if text.count(before) != 1:
        raise SystemExit(f'unreviewed Control Center source: {name}')
    return text.replace(before, after, 1)


def append_api(text, body, name):
    # Add an adapter API while retaining every existing provider/handler byte.
    closing = re.search(r'}\n*$', text)
    if not closing:
        raise SystemExit(f'unreviewed Control Center closing scope: {name}')
    return text[:closing.start()] + body + text[closing.start():]


def prepare(root):
    lock = json.loads((HERE / 'source.lock.json').read_text())
    expected = lock['files']
    for path in [root / BASE, *(root / BASE).parents, *(root / BASE).rglob('*')]:
        if path.is_symlink():
            raise SystemExit(f'Control Center source is a symlink: {path}')
    actual = {p.relative_to(root / BASE).as_posix(): digest(p.read_bytes())
              for p in (root / BASE).rglob('*') if p.is_file()}
    if actual != expected:
        differing = sorted(set(actual) ^ set(expected) |
                           {p for p in actual.keys() & expected.keys() if actual[p] != expected[p]})
        raise SystemExit('unreviewed Control Center package files: ' + ', '.join(differing[:8]))
    def read(name):
        return (root / BASE / name).read_bytes().decode()
    outputs = {}
    def put(name, text):
        outputs[BASE / name] = text.encode()

    main = read('contents/ui/main.qml')
    main = replace(main, 'import QtQuick 2.15\n', 'import QtQuick 2.15\nimport QtQuick.Window\n', 'screen dimensions import')
    main = replace(main, '''    property int fullRepWidth: {\x20
        switch (plasmoid.configuration.layout) {
            case 0: return 420 * scale;
            case 3: return 330 * scale;
            case 4: return 330 * scale; //custom/
            default: return 380 * scale
        }
    }''', '    property int fullRepWidth: 460 * scale', 'panel dimensions')
    main = replace(main, 'property int fullRepHeight: 380 * scale',
                   'property int fullRepHeight: Math.max(240, Math.min(688 * scale, '
                   '(Screen.desktopAvailableHeight > 0 ? Math.min(Screen.height, Screen.desktopAvailableHeight) : Screen.height) - 96))',
                   'panel height')
    main = replace(main, 'Qt.resolvedUrl("../assets/control.png")', 'Qt.resolvedUrl("../assets/xodus-controls.svg")', 'panel glyph')
    put('contents/ui/main.qml', main)

    full = read('contents/ui/FullRepresentation.qml')
    full = replace(full, '''    property var layouts : [
        "layouts/Default.qml",\x20
        "layouts/ControlCenter.qml",
        "layouts/Flat.qml",
        "layouts/Tahoe.qml",
        "layouts/Custom.qml"
    ]''', '    property var layouts : ["layouts/Xodus.qml"]', 'layout inventory')
    full = replace(full, 'source: fullRep.layouts[plasmoid.configuration.layout]', 'source: fullRep.layouts[0]', 'active layout')
    put('contents/ui/FullRepresentation.qml', full)

    compact = read('contents/ui/CompactRepresentation.qml')
    compact = replace(compact, 'Qt.resolvedUrl("../assets/control.png")', 'Qt.resolvedUrl("../assets/xodus-controls.svg")', 'compact glyph')
    put('contents/ui/CompactRepresentation.qml', compact)

    appearance = read('contents/ui/config/configAppearance.qml')
    appearance = replace(appearance, '''            model: [
                i18n("KDE Control Station (Default)"),
                i18n("Control Center"),
                i18n("Flat"),
                i18n("Tahoe"),
                i18n("Custom")
            ]''', '            model: [i18n("Xodus")]', 'layout selector')
    appearance = replace(appearance, '            onActivated: toggleLayoutDefaults(index)', '            onActivated: cfg_layout = 0', 'layout selector callback')
    put('contents/ui/config/configAppearance.qml', appearance)

    config = read('contents/config/main.xml')
    for name, old, new in [('scale', '110', '100'), ('layout', '3', '0'),
                            ('transparency', 'true', 'false'),
                            ('customButtonImage', '../assets/control.png', '../assets/xodus-controls.svg'),
                            ('toggleButtonsColor', '#007aff', '#ad85f5'),
                            ('slidersColor', '#ffffff', '#ad85f5')]:
        pattern = rf'(<entry name="{name}"[^>]*>.*?<default>){re.escape(old)}(</default>)'
        config, count = re.subn(pattern, lambda m: m[1] + new + m[2], config, flags=re.S)
        if count != 1:
            raise SystemExit(f'unreviewed Control Center default: {name}')
    put('contents/config/main.xml', config)

    additions = {
        'NetworkBtn.qml': '''\n    // Xodus frontend API; same reviewed wireless action as the original icon.
    function xodusToggleWireless() {
        if (!wifiCheckVisible) return;
        if (!isAirplane) network.handler.enableWireless(!wifiCheckChecked);
        else {
            network.handler.enableAirplaneMode(false);
            PlasmaNM.Configuration.airplaneModeEnabled = false;
        }
    }
''',
        'DndButton.qml': '''\n    // Public state for the Xodus view; original notification actions remain.
    readonly property bool xodusActive: Funcs.checkInhibition()
''',
        'Volume.qml': '''\n    // Frontend percent API; the existing PulseAudio sink still owns volume.
    function xodusSetPercent(percent) {
        if (sink) sink.volume = Math.max(0, Math.min(100, percent)) * Vol.PulseAudio.NormalVolume / 100;
    }
''',
        'BrightnessSlider.qml': '''\n    // Frontend percent API for the original first-display controller.
    readonly property bool xodusBrightnessAvailable: sbControl.isBrightnessAvailable && !!mainScreen && mainScreen.maxBrightness > 0
    readonly property real xodusPercent: xodusBrightnessAvailable ? mainScreen.brightness / mainScreen.maxBrightness * 100 : 0
    function xodusSetPercent(percent) {
        if (!xodusBrightnessAvailable) return;
        const minimum = mainScreen.maxBrightness > 100 ? 1 : 0;
        const value = Math.max(minimum, Math.min(mainScreen.maxBrightness, percent * mainScreen.maxBrightness / 100));
        sbControl.setBrightness(mainScreen.displayName, value);
    }
    function xodusOpenDetails() {
        fullRep.togglePage(fullRep.defaultInitialWidth, brightnessControlPage.contentItemHeight + brightnessControlPage.headerHeight, brightnessControlPage);
    }
''',
    }
    for name, body in additions.items():
        relative = 'contents/ui/components/' + name
        put(relative, append_api(read(relative), body, relative))

    payload_files = {p.relative_to(HERE / 'payload').as_posix(): digest(p.read_bytes())
                     for p in (HERE / 'payload').rglob('*') if p.is_file()}
    if payload_files != lock['payload']:
        raise SystemExit('Control Center payload inventory differs')
    for path in (HERE / 'payload').rglob('*'):
        if path.is_file():
            relative = path.relative_to(HERE / 'payload').as_posix()
            data = path.read_bytes()
            if digest(data) != lock['payload'][relative]:
                raise SystemExit(f'Control Center payload changed: {relative}')
            outputs[BASE / 'contents' / relative] = data
    for path in outputs:
        if (root / path).is_symlink():
            raise SystemExit(f'Control Center target is a symlink: {path}')
    return outputs


def apply(root):
    root = root.resolve(strict=True)
    updates = prepare(root)
    lock = json.loads((HERE / 'source.lock.json').read_text())
    derived = dict(lock['files'])
    derived.update({relative.relative_to(BASE).as_posix(): digest(data) for relative, data in updates.items()})
    if derived != lock['deployed']:
        raise SystemExit('Control Center transformation differs from reviewed derivation')
    marker = root / RECEIPT
    if any(path.is_symlink() for path in [marker, *marker.parents]):
        raise SystemExit('Control Center receipt path is a symlink')
    for relative, data in updates.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(receipt(lock))
    verify(root)
    print(f'Applied Xodus Control Center: {len(updates)} frontend files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live_root', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify(args.live_root)
        print('Verified Xodus Control Center deployed derivation')
    else:
        apply(args.live_root)

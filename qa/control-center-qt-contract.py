#!/usr/bin/env python3
"""Render the real Xodus QML and exercise its adapter with controlled providers.

Requires Qt 6 qmltestrunner, QtQuick Controls, Layouts and QtTest. The provider
fixtures cannot run host commands, change hardware or terminate a session.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--render-dir', type=Path, required=True)
parser.add_argument('--qmltestrunner', default='/usr/lib/qt6/bin/qmltestrunner'
                    if Path('/usr/lib/qt6/bin/qmltestrunner').is_file()
                    else shutil.which('qmltestrunner6') or shutil.which('qmltestrunner'))
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
payload = repo / 'overlay/identity/control-center/payload/ui/xodus'
render = args.render_dir.resolve()
render.mkdir(parents=True, exist_ok=True)

components = {
    'NetworkBtn': '''property string title: "Xodus Studio"
        property bool wifiCheckChecked: true
        property bool wifiCheckVisible: true
        function xodusToggleWireless() { wifiCheckChecked = !wifiCheckChecked; service.last = "wifi" }
        onClicked: service.last = "network-page"''',
    'BluetoothBtn': '''property string title: "Headphones"
        property QtObject btManager: QtObject { property bool bluetoothOperational: true; property var adapters: [1] }
        onClicked: service.last = "bluetooth-page"''',
    'BrightnessSlider': '''property bool xodusBrightnessAvailable: true
        property real xodusPercent: 68
        function xodusSetPercent(percent) { xodusPercent = percent; service.brightness = percent }
        function xodusOpenDetails() { service.last = "brightness-page" }''',
    'Volume': '''property bool sinkAvailable: true
        property real value: 42
        function xodusSetPercent(percent) { value = percent; service.volume = percent }
        onClicked: service.last = "volume-page"''',
    'DndButton': '''property bool xodusActive: false
        onClicked: { xodusActive = !xodusActive; service.last = "focus" }''',
    'ColorSchemeSwitcher': '''property bool isDarkMode: true
        onClicked: { isDarkMode = !isDarkMode; service.last = "appearance" }''',
    'NightLight': 'onClicked: service.last = "night-light-page"',
    'KDEConnect': 'onClicked: service.last = "devices"',
    'ScreenshotBtn': 'onClicked: service.last = "screenshot"',
    'SystemActions': 'onClicked: service.last = "power-confirmation-page"',
    'CommandRun': '''property string title
        property string command
        property string icon
        onClicked: service.last = command''',
}

test = r'''
import QtQuick
import QtTest
import "ui/xodus" as Xodus

Item {
    id: root
    width: 500; height: 780
    property bool isOpen: true
    property bool showMediaPlayer: true
    property bool showBrightness: true
    property bool showVolume: true
    property bool showDnd: true
    property bool showNightLight: true
    property bool showColorSwitcher: true
    property bool showKDEConnect: true
    property bool showScreenshot: true
    property bool showSessionActions: true
    property bool showBattery: true
    property bool showCmd1: false
    property bool showCmd2: false
    property string cmdTitle1: "Command one"
    property string cmdTitle2: "Command two"
    property string cmdRun1: "controlled-one"
    property string cmdRun2: "controlled-two"
    property string cmdIcon1: "controls"
    property string cmdIcon2: "controls"
    QtObject { id: service; property string last: ""; property real brightness: -1; property real volume: -1 }
    QtObject {
        id: mediaPlayerPage
        property string track: "Across the horizon"
        property string artist: "Xodus Session"
        property string albumArt: ""
        property bool isPlaying: true
        property bool canGoPrevious: true
        property bool canGoNext: true
        property bool canPause: true
        property bool canPlay: true
        function previous() { service.last = "previous" }
        function next() { service.last = "next" }
        function togglePlaying() { isPlaying = !isPlaying; service.last = "play-pause" }
    }
    QtObject {
        id: bluetoothPage
        function setBluetoothEnabled(enabled) {
            findProvider("BluetoothBtn").btManager.bluetoothOperational = enabled
            service.last = "bluetooth"
        }
    }
    QtObject {
        id: batteryPage
        property QtObject batteryControl: QtObject { property bool hasBatteries: true; property int percent: 72; property bool pluggedIn: false }
        property int contentItemHeight: 200
        property int headerHeight: 40
    }
    QtObject {
        id: fullRep
        property int defaultInitialWidth: 460
        property int defaultInitialHeight: 688
        function togglePage(width, height, page) { service.last = page === mediaPlayerPage ? "media-page" : "battery-page" }
    }
    function findProvider(name) { return tests.findChild(panel, "provider-" + name) }
    Xodus.ControlPanel {
        id: panel
        x: 20; y: 20
        width: 460; height: implicitHeight
        controller: Xodus.Controller { id: adapter }
    }
    TestCase {
        id: tests
        name: "XodusControlCenter"
        when: windowShown
        function click(name) {
            const item = findChild(panel, name)
            verify(item !== null, name)
            verify(item.visible, name + " visible")
            mouseClick(item)
            wait(15)
        }
        function test_01_render_and_connectivity() {
            waitForRendering(panel)
            compare(panel.width, 460)
            verify(panel.height >= 620 && panel.height <= 740, "Panel fits a 768px desktop: " + panel.height)
            grabImage(panel).save(@@NORMAL@@)
            click("network-toggle"); compare(service.last, "wifi"); compare(adapter.wifiEnabled, false)
            click("network-toggle"); compare(adapter.wifiEnabled, true)
            click("network-details"); compare(service.last, "network-page")
            click("bluetooth-toggle"); compare(service.last, "bluetooth"); compare(adapter.bluetoothEnabled, false)
            click("bluetooth-toggle"); compare(adapter.bluetoothEnabled, true)
            click("bluetooth-details"); compare(service.last, "bluetooth-page")
        }
        function test_02_media_and_levels() {
            click("previous"); compare(service.last, "previous")
            click("play-pause"); compare(service.last, "play-pause"); compare(adapter.playing, false)
            click("next"); compare(service.last, "next")
            click("media-details"); compare(service.last, "media-page")
            const brightness = findChild(panel, "brightness-slider")
            mouseClick(brightness, brightness.width * 0.8, brightness.height / 2)
            verify(service.brightness > 70 && service.brightness < 90)
            const volume = findChild(panel, "volume-slider")
            mouseClick(volume, volume.width * 0.3, volume.height / 2)
            verify(service.volume > 20 && service.volume < 40)
            volume.forceActiveFocus()
            keyClick(Qt.Key_Right)
            verify(service.volume > 20 && service.volume < 40)
            click("brightness-details"); compare(service.last, "brightness-page")
            click("volume-details"); compare(service.last, "volume-page")
        }
        function test_03_tools_and_confirmation() {
            click("focus-toggle"); compare(service.last, "focus"); compare(adapter.focusEnabled, true)
            click("night-light-toggle"); compare(service.last, "night-light-page")
            click("appearance-toggle"); compare(service.last, "appearance"); compare(adapter.darkMode, false)
            click("devices-toggle"); compare(service.last, "devices")
            click("screenshot-toggle"); compare(service.last, "screenshot")
            click("power-toggle"); compare(service.last, "power-confirmation-page")
            click("battery-details"); compare(service.last, "battery-page")
            showCmd1 = true; showCmd2 = true
            wait(30)
            click("command-one-toggle"); compare(service.last, "controlled-one")
            click("command-two-toggle"); compare(service.last, "controlled-two")
            showCmd1 = false; showCmd2 = false
        }
        function test_04_small_desktop_keyboard() {
            root.height = 600
            panel.height = 504
            compare(panel.width, 460)
            const power = findChild(panel, "power-toggle")
            const scroll = findChild(panel, "control-scroll")
            findChild(panel, "close").forceActiveFocus()
            for (let i = 0; i < 32 && !power.activeFocus; ++i) {
                keyClick(Qt.Key_Tab)
                wait(5)
            }
            verify(power.activeFocus, "Power reachable by keyboard")
            const card = findChild(panel, "power")
            const position = card.mapToItem(scroll, 0, 0)
            verify(position.y >= 0 && position.y + card.height <= scroll.height, "Entire focused Power card remains visible")
            keyClick(Qt.Key_Space)
            compare(service.last, "power-confirmation-page")
            waitForRendering(panel)
            grabImage(panel).save(@@SMALL@@)
            panel.height = Qt.binding(() => panel.implicitHeight)
            root.height = 780
        }
        function test_05_unavailable_providers() {
            findProvider("NetworkBtn").wifiCheckVisible = false
            findProvider("BluetoothBtn").btManager.adapters = []
            findProvider("BrightnessSlider").xodusBrightnessAvailable = false
            findProvider("Volume").sinkAvailable = false
            mediaPlayerPage.canGoPrevious = false
            mediaPlayerPage.canGoNext = false
            mediaPlayerPage.canPause = false
            mediaPlayerPage.canPlay = false
            mediaPlayerPage.track = ""; mediaPlayerPage.artist = ""
            wait(50)
            for (const name of ["network-toggle", "bluetooth-toggle", "brightness-slider", "volume-slider", "previous", "next", "play-pause"])
                verify(!findChild(panel, name).enabled, name + " must be disabled")
            grabImage(panel).save(@@UNAVAILABLE@@)
            const before = service.last
            mouseClick(findChild(panel, "power-toggle"))
            compare(service.last, "power-confirmation-page")
            click("close"); compare(root.isOpen, false)
        }
    }
}
'''

with tempfile.TemporaryDirectory(prefix='xodus-control-qt-') as temporary:
    base = Path(temporary)
    shutil.copytree(payload, base / 'ui/xodus')
    providers = base / 'ui/components'
    providers.mkdir()
    for name, body in components.items():
        (providers / (name + '.qml')).write_text(
            'import QtQuick\nItem {\nobjectName: "provider-' + name + '"\nsignal clicked()\n' + body + '\n}\n')
    test = test.replace('@@NORMAL@@', json.dumps(str(render / 'xodus-control-center.png')))
    test = test.replace('@@UNAVAILABLE@@', json.dumps(str(render / 'xodus-control-center-unavailable.png')))
    test = test.replace('@@SMALL@@', json.dumps(str(render / 'xodus-control-center-600.png')))
    (base / 'tst_control.qml').write_text(test)
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
    result = subprocess.run([args.qmltestrunner, '-input', str(base), '-o', '-,txt'],
                            env=environment, capture_output=True, text=True, timeout=90)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode:
        raise SystemExit(result.returncode)
    assert (render / 'xodus-control-center.png').is_file()
    assert (render / 'xodus-control-center-unavailable.png').is_file()
    assert (render / 'xodus-control-center-600.png').is_file()
print('PASS: real Qt view and controller adapter; connectivity, media, levels, tools and unavailable states')

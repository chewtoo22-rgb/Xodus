import QtQuick
import "../components" as Components

// Frontend adapter. The audited components and detail pages own the services.
Item {
    id: controller
    visible: false
    width: 0
    height: 0
    readonly property string networkLabel: networkProxy.title
    readonly property bool wifiEnabled: networkProxy.wifiCheckChecked
    readonly property bool wifiAvailable: networkProxy.wifiCheckVisible
    readonly property string bluetoothLabel: bluetoothProxy.title
    readonly property bool bluetoothEnabled: bluetoothProxy.btManager.bluetoothOperational
    readonly property bool bluetoothAvailable: bluetoothProxy.btManager.adapters.length > 0
    readonly property string track: mediaPlayerPage.track
    readonly property string artist: mediaPlayerPage.artist
    readonly property string albumArt: mediaPlayerPage.albumArt
    readonly property bool playing: mediaPlayerPage.isPlaying
    readonly property bool canPrevious: mediaPlayerPage.canGoPrevious
    readonly property bool canNext: mediaPlayerPage.canGoNext
    readonly property bool canPlayPause: playing ? mediaPlayerPage.canPause : mediaPlayerPage.canPlay
    readonly property bool brightnessAvailable: brightnessProxy.xodusBrightnessAvailable
    readonly property real brightness: brightnessProxy.xodusPercent
    readonly property bool volumeAvailable: volumeProxy.sinkAvailable
    readonly property real volume: volumeProxy.value
    readonly property bool focusEnabled: focusProxy.xodusActive
    readonly property bool darkMode: appearanceProxy.isDarkMode
    readonly property bool showMedia: root.showMediaPlayer
    readonly property bool showBrightness: root.showBrightness
    readonly property bool showVolume: root.showVolume
    readonly property bool showFocus: root.showDnd
    readonly property bool showNightLight: root.showNightLight
    readonly property bool showAppearance: root.showColorSwitcher
    readonly property bool showDevices: root.showKDEConnect
    readonly property bool showScreenshot: root.showScreenshot
    readonly property bool showPower: root.showSessionActions
    readonly property bool showBattery: root.showBattery && batteryPage.batteryControl.hasBatteries
    readonly property string batteryLabel: batteryPage.batteryControl.percent + "% · " + (batteryPage.batteryControl.pluggedIn ? qsTr("Connected to power") : qsTr("On battery"))
    readonly property bool showCommandOne: root.showCmd1
    readonly property bool showCommandTwo: root.showCmd2
    readonly property string commandOneTitle: root.cmdTitle1
    readonly property string commandTwoTitle: root.cmdTitle2

    function toggleWifi() { networkProxy.xodusToggleWireless() }
    function openNetwork() { networkProxy.clicked() }
    function toggleBluetooth() { bluetoothPage.setBluetoothEnabled(!bluetoothEnabled) }
    function openBluetooth() { bluetoothProxy.clicked() }
    function previous() { mediaPlayerPage.previous() }
    function next() { mediaPlayerPage.next() }
    function playPause() { mediaPlayerPage.togglePlaying() }
    function openMedia() { fullRep.togglePage(fullRep.defaultInitialWidth, fullRep.defaultInitialHeight, mediaPlayerPage) }
    function setBrightness(percent) { brightnessProxy.xodusSetPercent(percent) }
    function openBrightness() { brightnessProxy.xodusOpenDetails() }
    function setVolume(percent) { volumeProxy.xodusSetPercent(percent) }
    function openVolume() { volumeProxy.clicked() }
    function toggleFocus() { focusProxy.clicked() }
    function openNightLight() { nightProxy.clicked() }
    function toggleAppearance() { appearanceProxy.clicked() }
    function openDevices() { devicesProxy.clicked() }
    function takeScreenshot() { screenshotProxy.clicked() }
    function openPower() { powerProxy.clicked() }
    function openBattery() { fullRep.togglePage(fullRep.defaultInitialWidth, batteryPage.contentItemHeight + batteryPage.headerHeight, batteryPage) }
    function runCommandOne() { commandOneProxy.clicked() }
    function runCommandTwo() { commandTwoProxy.clicked() }
    function close() { root.isOpen = false }

    Components.NetworkBtn { id: networkProxy; visible: false }
    Components.BluetoothBtn { id: bluetoothProxy; visible: false }
    Components.BrightnessSlider { id: brightnessProxy; visible: false }
    Components.Volume { id: volumeProxy; visible: false }
    Components.DndButton { id: focusProxy; visible: false }
    Components.NightLight { id: nightProxy; visible: false }
    Components.ColorSchemeSwitcher { id: appearanceProxy; visible: false }
    Components.KDEConnect { id: devicesProxy; visible: false }
    Components.ScreenshotBtn { id: screenshotProxy; visible: false }
    Components.SystemActions { id: powerProxy; visible: false }
    Components.CommandRun { id: commandOneProxy; visible: false; command: root.cmdRun1; title: root.cmdTitle1; icon: root.cmdIcon1 }
    Components.CommandRun { id: commandTwoProxy; visible: false; command: root.cmdRun2; title: root.cmdTitle2; icon: root.cmdIcon2 }
}

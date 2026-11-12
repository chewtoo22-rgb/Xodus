import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Rectangle {
    id: panel
    required property var controller
    implicitWidth: 460
    implicitHeight: body.implicitHeight + 32
    radius: 20
    color: "#17141d"
    border.color: "#45374f"
    border.width: 1
    function reveal(item) {
        let ancestor = item
        let visibleItem = item
        while (ancestor && ancestor !== body) {
            if (ancestor.subtitle !== undefined || ancestor.levelValue !== undefined) visibleItem = ancestor
            ancestor = ancestor.parent
        }
        if (!ancestor) return
        const point = visibleItem.mapToItem(body, 0, 0)
        const flick = scrolling.contentItem
        let position = flick.contentY
        if (point.y < position) position = point.y
        else if (point.y + visibleItem.height > position + scrolling.availableHeight)
            position = point.y + visibleItem.height - scrolling.availableHeight
        flick.contentY = Math.max(0, Math.min(scrolling.contentHeight - scrolling.availableHeight, position))
    }
    Connections {
        target: panel.Window.window
        function onActiveFocusItemChanged() {
            if (target.activeFocusItem) panel.reveal(target.activeFocusItem)
        }
    }
    ScrollView {
        id: scrolling
        objectName: "control-scroll"
        anchors.fill: parent
        anchors.margins: 16
        clip: true
        contentWidth: availableWidth
        contentHeight: body.implicitHeight
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded
        ColumnLayout {
        id: body
        width: scrolling.availableWidth
        spacing: 8
        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 3
            ColumnLayout {
                spacing: 2
                Text { text: "XODUS"; color: "#ad85f5"; font.pixelSize: 10; font.weight: Font.Bold; font.letterSpacing: 2.8 }
                Text { text: qsTr("Control Center"); color: "#f5f3fa"; font.pixelSize: 22; font.weight: Font.DemiBold }
            }
            Item { Layout.fillWidth: true }
            ActionButton { objectName: "close"; symbol: "close"; accessibleLabel: qsTr("Close Control Center"); onClicked: controller.close() }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            ControlTile {
                objectName: "network"
                Layout.fillWidth: true
                title: qsTr("Wi-Fi")
                subtitle: controller.networkLabel
                symbol: "wifi"
                selected: controller.wifiEnabled
                available: controller.wifiAvailable
                showDetails: true
                onActivated: controller.toggleWifi()
                onDetailsRequested: controller.openNetwork()
            }
            ControlTile {
                objectName: "bluetooth"
                Layout.fillWidth: true
                title: qsTr("Bluetooth")
                subtitle: controller.bluetoothLabel
                symbol: "bluetooth"
                selected: controller.bluetoothEnabled
                available: controller.bluetoothAvailable
                showDetails: true
                onActivated: controller.toggleBluetooth()
                onDetailsRequested: controller.openBluetooth()
            }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 96
            visible: controller.showMedia
            radius: 14; color: "#211e29"; border.color: "#38313f"
            RowLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 12
                Rectangle {
                    implicitWidth: 58; implicitHeight: 58; radius: 12; color: "#352641"; clip: true
                    Image { anchors.fill: parent; source: controller.albumArt; fillMode: Image.PreserveAspectCrop; visible: status === Image.Ready }
                    Glyph { anchors.centerIn: parent; width: 28; height: 28; symbol: "music"; ink: "#ad85f5"; visible: !controller.albumArt }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 7
                    Text { text: controller.track || qsTr("No media playing"); Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: 13; font.weight: Font.DemiBold; color: "#f5f3fa" }
                    Text { text: controller.artist || qsTr("Your media appears here"); Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: 11; color: "#b9b0c7" }
                    RowLayout {
                        spacing: 7
                        ActionButton { objectName: "previous"; symbol: "previous"; accessibleLabel: qsTr("Previous track"); enabled: controller.canPrevious; implicitWidth: 28; implicitHeight: 28; padding: 7; onClicked: controller.previous() }
                        ActionButton { objectName: "play-pause"; symbol: controller.playing ? "pause" : "play"; accessibleLabel: controller.playing ? qsTr("Pause") : qsTr("Play"); enabled: controller.canPlayPause; accented: true; implicitWidth: 32; implicitHeight: 28; padding: 7; onClicked: controller.playPause() }
                        ActionButton { objectName: "next"; symbol: "next"; accessibleLabel: qsTr("Next track"); enabled: controller.canNext; implicitWidth: 28; implicitHeight: 28; padding: 7; onClicked: controller.next() }
                    }
                }
                ActionButton { objectName: "media-details"; symbol: "arrow"; accessibleLabel: qsTr("Media players"); onClicked: controller.openMedia() }
            }
        }
        LevelControl { objectName: "brightness"; Layout.fillWidth: true; title: qsTr("Brightness"); symbol: "brightness"; visible: controller.showBrightness; available: controller.brightnessAvailable; levelValue: controller.brightness; onLevelMoved: percent => controller.setBrightness(percent); onDetailsRequested: controller.openBrightness() }
        LevelControl { objectName: "volume"; Layout.fillWidth: true; title: qsTr("Volume"); symbol: "volume"; visible: controller.showVolume; available: controller.volumeAvailable; levelValue: controller.volume; onLevelMoved: percent => controller.setVolume(percent); onDetailsRequested: controller.openVolume() }
        GridLayout {
            columns: 2; rowSpacing: 10; columnSpacing: 10
            Layout.fillWidth: true
            ControlTile { objectName: "focus"; Layout.fillWidth: true; title: qsTr("Focus"); subtitle: controller.focusEnabled ? qsTr("Notifications paused") : qsTr("Notifications on"); symbol: "focus"; visible: controller.showFocus; selected: controller.focusEnabled; onActivated: controller.toggleFocus() }
            ControlTile { objectName: "night-light"; Layout.fillWidth: true; title: qsTr("Night light"); subtitle: qsTr("Display warmth"); symbol: "night"; visible: controller.showNightLight; onActivated: controller.openNightLight() }
            ControlTile { objectName: "appearance"; Layout.fillWidth: true; title: qsTr("Appearance"); subtitle: controller.darkMode ? qsTr("Dark mode") : qsTr("Light mode"); symbol: "theme"; visible: controller.showAppearance; selected: controller.darkMode; onActivated: controller.toggleAppearance() }
            ControlTile { objectName: "devices"; Layout.fillWidth: true; title: qsTr("Devices"); subtitle: qsTr("Connect your phone"); symbol: "devices"; visible: controller.showDevices; onActivated: controller.openDevices() }
            ControlTile { objectName: "screenshot"; Layout.fillWidth: true; title: qsTr("Screenshot"); subtitle: qsTr("Capture your screen"); symbol: "screenshot"; visible: controller.showScreenshot; onActivated: controller.takeScreenshot() }
            ControlTile { objectName: "power"; Layout.fillWidth: true; title: qsTr("Power"); subtitle: qsTr("Session actions"); symbol: "power"; visible: controller.showPower; onActivated: controller.openPower() }
            ControlTile { objectName: "command-one"; Layout.fillWidth: true; title: controller.commandOneTitle; symbol: "controls"; visible: controller.showCommandOne; onActivated: controller.runCommandOne() }
            ControlTile { objectName: "command-two"; Layout.fillWidth: true; title: controller.commandTwoTitle; symbol: "controls"; visible: controller.showCommandTwo; onActivated: controller.runCommandTwo() }
        }
        Button {
            objectName: "battery-details"
            visible: controller.showBattery
            Layout.fillWidth: true
            text: controller.batteryLabel
            flat: true
            Accessible.name: text
            background: Rectangle { color: "transparent"; radius: 8; border.color: parent.activeFocus ? "#ad85f5" : "transparent" }
            contentItem: Text { text: parent.text; font.pixelSize: 11; color: "#b9b0c7"; horizontalAlignment: Text.AlignLeft }
            onClicked: controller.openBattery()
        }
    }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

PageBase {
    title: "About Xodus"
    Component.onCompleted: SysInfo.refresh()
    SettingsCard {
        RowLayout {
            width: parent.width; spacing: 20
            Image {
                source: "file:///usr/share/pixmaps/xodus-app-icon.png"
                Layout.preferredWidth: 86; Layout.preferredHeight: 86
                fillMode: Image.PreserveAspectFit
            }
            Column {
                Layout.fillWidth: true; spacing: 8
                Text { text: "XODUS"; font.pixelSize: 30; font.letterSpacing: 5; font.weight: Font.DemiBold; color: Theme.textPrimary }
                Text { text: "Rolling release" + (SysInfo.osVersion ? " · base " + SysInfo.osVersion : ""); font.pixelSize: 15; color: Theme.accent }
                Text { text: "Your desktop. Your direction."; font.pixelSize: 13; color: Theme.textSecondary }
            }
        }
    }
    Spacer { height: 26 }
    SectionTitle { text: "This computer" }
    SettingsCard {
        Column {
            width: parent.width; spacing: 0
            Repeater {
                model: [
                    { label: "Device name", value: SysInfo.hostName || "Loading…" },
                    { label: "Processor", value: SysInfo.cpuModel || "Loading…" },
                    { label: "Memory", value: SysInfo.totalRam > 0 ? (SysInfo.totalRam / 1073741824).toFixed(1) + " GB" : "Loading…" },
                    { label: "Graphics", value: SysInfo.gpuModel || "Unavailable" },
                    { label: "Kernel", value: SysInfo.kernelVersion || "Loading…" },
                    { label: "Storage", value: SysInfo.totalDisk > 0 ? (SysInfo.totalDisk / 1073741824).toFixed(1) + " GB" : "Loading…" }
                ]
                delegate: Column {
                    width: parent.width; spacing: 0
                    RowLayout {
                        width: parent.width; height: Math.max(46, valueText.implicitHeight + 18); spacing: 18
                        Text { text: modelData.label; color: Theme.textSecondary; font.pixelSize: 13; Layout.preferredWidth: 112 }
                        Text { id: valueText; text: modelData.value; color: Theme.textPrimary; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight }
                    }
                    Rectangle { width: parent.width; height: 1; color: Theme.divider; visible: index < 5 }
                }
            }
        }
    }
    Spacer { height: 20 }
    Row {
        width: parent.width; spacing: 20
        Text {
            text: "Storage details →"; color: Theme.accent; font.pixelSize: 13
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Navigator.navigateTo(30) }
        }
        Text {
            text: "Check for updates →"; color: Theme.accent; font.pixelSize: 13
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Navigator.navigateTo(29) }
        }
    }
    Spacer { height: 24 }
    Text {
        width: parent.width
        text: "Built with open source software."
        color: Theme.textTertiary; font.pixelSize: 11; wrapMode: Text.WordWrap
    }
    Spacer { height: 8 }
    Button {
        id: licensesButton
        text: "View licenses →"
        font.pixelSize: 12
        padding: 9
        Accessible.name: "View open source licenses"
        contentItem: Text {
            text: licensesButton.text; font: licensesButton.font
            color: Theme.accent
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 6; color: licensesButton.hovered ? Theme.hoverBg : "transparent"
            border.width: licensesButton.activeFocus ? 1 : 0
            border.color: Theme.accent
        }
        onClicked: Qt.openUrlExternally("file:///usr/share/licenses/xodus-settings")
    }
}

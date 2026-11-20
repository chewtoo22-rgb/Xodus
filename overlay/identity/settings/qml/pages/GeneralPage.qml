import QtQuick
import QtQuick.Layouts
import "../components"

PageBase {
    title: "General"
    Text {
        width: parent.width
        text: "Keep your system up to date and make it yours."
        color: Theme.textSecondary; font.pixelSize: 15; wrapMode: Text.WordWrap
    }
    Spacer { height: 24 }
    SettingsCard {
        Column {
            width: parent.width
            Repeater {
                model: [
                    { label: "About Xodus", detail: "System version and device information", idx: 28 },
                    { label: "Software Update", detail: "Review and install package updates", idx: 29 },
                    { label: "Storage", detail: "See how your disk space is used", idx: 30 },
                    { label: "Date and Time", detail: "Time zone and clock preferences", idx: 31 },
                    { label: "Users and Groups", detail: "Manage local accounts", idx: 20 },
                    { label: "Privacy and Security", detail: "Permissions and system protection", idx: 18 }
                ]
                delegate: Rectangle {
                    id: row
                    width: parent.width; height: 76; radius: 6
                    color: hit.containsMouse ? Theme.hoverBg : "transparent"
                    Column {
                        anchors.left: parent.left; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                        Text { text: modelData.label; font.pixelSize: 14; font.weight: Font.DemiBold; color: Theme.textPrimary }
                        Text { text: modelData.detail; font.pixelSize: 12; color: Theme.textSecondary }
                    }
                    Text { text: "›"; font.pixelSize: 24; color: Theme.accent; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter }
                    MouseArea { id: hit; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Navigator.navigateTo(modelData.idx) }
                    Rectangle { width: parent.width; height: 1; color: Theme.divider; anchors.bottom: parent.bottom; visible: index < 5 }
                }
            }
        }
    }
}

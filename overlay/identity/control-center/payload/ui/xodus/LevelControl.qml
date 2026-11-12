import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: level
    property string title
    property string symbol
    property bool available: true
    property real levelValue: 0
    property bool showDetails: true
    signal levelMoved(real percent)
    signal detailsRequested()
    implicitHeight: 84
    radius: 14
    color: "#211e29"
    border.color: "#38313f"
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 3
        RowLayout {
            Glyph { symbol: level.symbol; implicitWidth: 18; implicitHeight: 18; ink: "#ad85f5" }
            Text { text: level.title; color: "#f5f3fa"; font.pixelSize: 12; font.weight: Font.DemiBold; Layout.fillWidth: true }
            Text { text: level.available ? Math.round(level.levelValue) + "%" : qsTr("Unavailable"); color: "#b9b0c7"; font.pixelSize: 11 }
            ActionButton {
                objectName: level.objectName + "-details"
                symbol: "arrow"
                accessibleLabel: level.title + " settings"
                visible: level.showDetails
                implicitWidth: 24; implicitHeight: 24; padding: 6
                onClicked: level.detailsRequested()
            }
        }
        Slider {
            id: slider
            objectName: level.objectName + "-slider"
            Layout.fillWidth: true
            from: 0; to: 100
            value: level.levelValue
            enabled: level.available
            Accessible.name: level.title
            Accessible.role: Accessible.Slider
            onMoved: level.levelMoved(value)
            background: Rectangle {
                x: slider.leftPadding; y: slider.topPadding + slider.availableHeight / 2 - height / 2
                width: slider.availableWidth; height: 6; radius: 3
                color: "#3c3548"
                Rectangle { width: slider.visualPosition * parent.width; height: parent.height; radius: 3; color: slider.enabled ? "#ad85f5" : "#69616f" }
            }
            handle: Rectangle {
                x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                y: slider.topPadding + slider.availableHeight / 2 - height / 2
                implicitWidth: 17; implicitHeight: 17; radius: 9
                color: slider.pressed ? "#d6baff" : "#f5f3fa"
                border.color: slider.activeFocus ? "#ad85f5" : "#211e29"
                border.width: 2
                opacity: slider.enabled ? 1 : 0.45
            }
        }
    }
}

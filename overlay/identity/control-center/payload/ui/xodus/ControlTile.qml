import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: tile
    property string title
    property string subtitle
    property string symbol
    property bool selected: false
    property bool available: true
    property bool showDetails: false
    signal activated()
    signal detailsRequested()
    implicitHeight: 64
    radius: 14
    color: selected ? "#30233f" : "#211e29"
    border.width: 1
    border.color: selected ? "#7959a3" : "#38313f"
    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10
        ActionButton {
            objectName: tile.objectName + "-toggle"
            symbol: tile.symbol
            accessibleLabel: tile.title
            accented: tile.selected
            enabled: tile.available
            onClicked: tile.activated()
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            Text { text: tile.title; color: "#f5f3fa"; font.pixelSize: 13; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
            Text { text: tile.subtitle; color: "#b9b0c7"; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight; visible: text.length > 0 }
        }
        ActionButton {
            objectName: tile.objectName + "-details"
            visible: tile.showDetails
            symbol: "arrow"
            accessibleLabel: tile.title + " settings"
            implicitWidth: 28
            implicitHeight: 32
            padding: 7
            onClicked: tile.detailsRequested()
        }
    }
}

import QtQuick
import QtQuick.Controls

Button {
    id: action
    property string symbol: "controls"
    property bool accented: false
    property string accessibleLabel: text
    implicitWidth: 38
    implicitHeight: 38
    hoverEnabled: true
    Accessible.name: accessibleLabel
    Accessible.role: Accessible.Button
    background: Rectangle {
        radius: 10
        color: action.down ? "#7250ac" : action.accented ? "#ad85f5" : action.hovered ? "#34303f" : "#25212d"
        border.color: action.activeFocus ? "#d8c2ff" : "#423a50"
        border.width: action.activeFocus ? 2 : 1
        opacity: action.enabled ? 1 : 0.4
    }
    contentItem: Glyph {
        symbol: action.symbol
        ink: action.accented ? "#15121b" : "#f5f3fa"
        opacity: action.enabled ? 1 : 0.4
    }
    padding: 10
    ToolTip.visible: hovered && accessibleLabel.length > 0
    ToolTip.text: accessibleLabel
}

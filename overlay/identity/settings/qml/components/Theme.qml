pragma Singleton
import QtQuick

QtObject {
    readonly property bool dark: Qt.styleHints.colorScheme !== Qt.ColorScheme.Light
    readonly property color bg: dark ? "#101015" : "#F5F3FA"
    readonly property color bgCard: dark ? "#1C1B24" : "#FFFFFF"
    readonly property color bgSidenav: dark ? "#14131B" : "#ECE8F4"
    readonly property color bgSearch: dark ? "#23212E" : "#FFFFFF"
    readonly property color textPrimary: dark ? "#F6F3FF" : "#21182F"
    readonly property color textSecondary: dark ? "#C7C1D6" : "#5C526D"
    readonly property color textTertiary: dark ? "#A7A0B7" : "#6B607B"
    readonly property color divider: dark ? "#36313F" : "#D8D0E4"
    readonly property color border: divider
    readonly property color accent: dark ? "#BC9BFF" : "#7040B8"
    readonly property string accentHex: dark ? "#BC9BFF" : "#7040B8"
    readonly property color activeBg: dark ? "#342A48" : "#DFD1F4"
    readonly property color hoverBg: dark ? "#292532" : "#E4DCEF"
    readonly property color toggleOff: dark ? "#5D556B" : "#9B8DAB"
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "pages"

ApplicationWindow {
    id: window
    width: 1040; height: 720
    minimumWidth: 880; minimumHeight: 600
    visible: true
    title: "Xodus Settings"
    color: Theme.bg
    readonly property string ap: "file:///usr/share/extras/system-settings/assets/"
    property string searchQuery: ""
    readonly property var menuItems: [
        { label: "About Xodus", idx: 28, group: "SYSTEM" },
        { label: "General", idx: 4, group: "" },
        { label: "Software Update", idx: 29, group: "" },
        { label: "Storage", idx: 30, group: "" },
        { label: "Wi-Fi", idx: 0, group: "CONNECTIONS" },
        { label: "Bluetooth", idx: 1, group: "" },
        { label: "Network", idx: 2, group: "" },
        { label: "Internet Accounts", idx: 21, group: "" },
        { label: "Appearance", idx: 6, group: "DESKTOP" },
        { label: "Desktop and Dock", idx: 9, group: "" },
        { label: "Menu Bar", idx: 7, group: "" },
        { label: "Wallpaper", idx: 11, group: "" },
        { label: "Notifications", idx: 13, group: "" },
        { label: "Search", idx: 12, group: "" },
        { label: "Displays", idx: 10, group: "DEVICE" },
        { label: "Sound", idx: 14, group: "" },
        { label: "Battery", idx: 3, group: "" },
        { label: "Keyboard", idx: 25, group: "" },
        { label: "Trackpad", idx: 26, group: "" },
        { label: "Printers and Scanners", idx: 27, group: "" },
        { label: "Users and Groups", idx: 20, group: "PERSONAL" },
        { label: "Privacy and Security", idx: 18, group: "" },
        { label: "Lock Screen", idx: 17, group: "" },
        { label: "Fingerprint and Password", idx: 19, group: "" },
        { label: "Accessibility", idx: 5, group: "" },
        { label: "Focus", idx: 15, group: "" },
        { label: "Screen Time", idx: 16, group: "" },
        { label: "Date and Time", idx: 31, group: "" }
    ]
    readonly property var pageComponents: [wifi, bluetooth, network, battery,
        general, accessibility, appearance, menubar, null, desktop, displays,
        wallpaper, spotlight, notifications, sound, focus, screenTime, lockscreen,
        privacy, touchid, users, internetAccounts, null, null, null, keyboard,
        trackpad, printers, about, updates, storage, datetime]
    readonly property string pageTitle: {
        for (var i = 0; i < menuItems.length; ++i)
            if (menuItems[i].idx === Navigator.currentIdx) return menuItems[i].label
        return "Settings"
    }
    Component.onCompleted: Navigator.navigateTo(XodusInitialPage)
    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.preferredWidth: 246; Layout.fillHeight: true
            color: Theme.bgSidenav
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 18; spacing: 18
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Image {
                        source: "file:///usr/share/pixmaps/xodus-app-icon.png"
                        Layout.preferredWidth: 42; Layout.preferredHeight: 42
                        fillMode: Image.PreserveAspectFit
                    }
                    Column {
                        spacing: 2
                        Text { text: "XODUS"; color: Theme.textPrimary; font.pixelSize: 18; font.letterSpacing: 3; font.weight: Font.DemiBold }
                        Text { text: "Settings"; color: Theme.textSecondary; font.pixelSize: 13 }
                    }
                }
                TextField {
                    id: search
                    Layout.fillWidth: true
                    placeholderText: "Search settings"
                    placeholderTextColor: Theme.textTertiary
                    color: Theme.textPrimary
                    onTextChanged: window.searchQuery = text.toLowerCase()
                    background: Rectangle { radius: 8; color: Theme.bgSearch; border.color: search.activeFocus ? Theme.accent : Theme.border }
                }
                ListView {
                    id: navigation
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; spacing: 3
                    model: window.menuItems.filter(function(item) { return item.label.toLowerCase().indexOf(window.searchQuery) >= 0 })
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    delegate: Column {
                        required property var modelData
                        width: navigation.width; spacing: 5
                        Text {
                            text: modelData.group
                            visible: text.length > 0 && window.searchQuery.length === 0
                            topPadding: 14; bottomPadding: 4; leftPadding: 10
                            color: Theme.textTertiary; font.pixelSize: 10; font.letterSpacing: 1.6
                        }
                        Button {
                            id: navButton
                            width: parent.width; height: 38
                            text: modelData.label
                            onClicked: Navigator.navigateTo(modelData.idx)
                            contentItem: Text {
                                text: navButton.text; color: Theme.textPrimary
                                font.pixelSize: 13; font.weight: Navigator.currentIdx === modelData.idx ? Font.DemiBold : Font.Normal
                                verticalAlignment: Text.AlignVCenter; leftPadding: 12; elide: Text.ElideRight
                            }
                            background: Rectangle {
                                radius: 8
                                color: Navigator.currentIdx === modelData.idx ? Theme.activeBg : navButton.hovered ? Theme.hoverBg : "transparent"
                                border.color: Navigator.currentIdx === modelData.idx ? Theme.accent : "transparent"
                            }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.border }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.margins: 22; spacing: 16
            RowLayout {
                Layout.fillWidth: true
                Text { text: window.pageTitle; color: Theme.textPrimary; font.pixelSize: 25; font.weight: Font.DemiBold; Layout.fillWidth: true }
                HistoryButton { text: "Back"; enabled: Navigator.canGoBack; onClicked: Navigator.goBack() }
                HistoryButton { text: "Forward"; enabled: Navigator.canGoForward; onClicked: Navigator.goForward() }
            }
            Loader {
                Layout.fillWidth: true; Layout.fillHeight: true
                sourceComponent: window.pageComponents[Navigator.currentIdx] || general
            }
        }
    }
    component HistoryButton: Button {
        id: button
        implicitWidth: 76; implicitHeight: 34
        contentItem: Text {
            text: button.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            font.pixelSize: 12; color: button.enabled ? Theme.textPrimary : Theme.textTertiary
        }
        background: Rectangle {
            radius: 7; color: button.hovered ? Theme.hoverBg : Theme.bgCard
            border.color: button.activeFocus ? Theme.accent : Theme.border
        }
        opacity: enabled ? 1 : 0.55
    }
    Component { id: wifi; WiFiPage {} }
    Component { id: bluetooth; BluetoothPage {} }
    Component { id: network; NetworkPage {} }
    Component { id: battery; BatteryPage {} }
    Component { id: general; GeneralPage {} }
    Component { id: accessibility; AccessibilityPage {} }
    Component { id: appearance; AppearancePage {} }
    Component { id: menubar; MenuBarPage {} }
    Component { id: desktop; DesktopDockPage {} }
    Component { id: displays; DisplaysPage {} }
    Component { id: wallpaper; WallpaperPage {} }
    Component { id: spotlight; SpotlightPage {} }
    Component { id: notifications; NotificationsPage {} }
    Component { id: sound; SoundPage {} }
    Component { id: focus; FocusPage {} }
    Component { id: screenTime; ScreenTimePage {} }
    Component { id: lockscreen; LockScreenPage {} }
    Component { id: privacy; PrivacyPage {} }
    Component { id: touchid; TouchIDPage {} }
    Component { id: users; UsersPage {} }
    Component { id: internetAccounts; InternetAccountsPage {} }
    Component { id: keyboard; KeyboardPage {} }
    Component { id: trackpad; TrackpadPage {} }
    Component { id: printers; PrintersPage {} }
    Component { id: about; AboutPage {} }
    Component { id: updates; SoftwareUpdatePage {} }
    Component { id: storage; StoragePage {} }
    Component { id: datetime; DateTimePage {} }
}

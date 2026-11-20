// Copyright 2026 Xodus contributors. SPDX-License-Identifier: MIT
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Control {
    id: root
    width: 1920
    height: 1080
    font.family: "Noto Sans"
    palette.window: "#08060D"
    palette.windowText: "#F6F2FF"
    palette.base: "#17121F"
    palette.text: "#F6F2FF"
    palette.placeholderText: "#AAA0B7"
    palette.button: "#AD85F5"
    palette.buttonText: "#100A1B"
    palette.highlight: "#AD85F5"
    palette.highlightedText: "#100A1B"
    palette.mid: "#51465F"
    LayoutMirroring.enabled: Qt.locale().textDirection === Qt.RightToLeft
    LayoutMirroring.childrenInherit: true
    property bool authenticating: false
    property bool manualAccount: false
    property string loginMessage: ""

    function signIn() {
        if (!authenticating && username.text.trim().length > 0) {
            loginMessage = ""
            authenticating = true
            sddm.login(username.text.trim(), password.text, session.currentIndex)
        }
    }

    background: Rectangle {
        color: "#08060D"
        Image {
            anchors.fill: parent
            source: "file:///usr/share/wallpapers/Xodus/xodus-wallpaper.png"
            fillMode: Image.PreserveAspectCrop
        }
        Rectangle { anchors.fill: parent; color: "#B508060D" }
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            root.authenticating = false
            root.loginMessage = qsTr("Sign in failed. Check your account and password.")
            password.text = ""
            password.forceActiveFocus()
        }
        function onLoginSucceeded() { root.loginMessage = qsTr("Starting your session…") }
    }

    Rectangle {
        id: card
        anchors.centerIn: parent
        anchors.verticalCenterOffset: -16
        width: Math.min(420, root.width - 48)
        height: form.implicitHeight + 56
        scale: Math.min(1, (root.height - 128) / height)
        radius: 20
        color: "#EF110D18"
        border.color: "#44364F"
        border.width: 1

        ColumnLayout {
            id: form
            anchors.fill: parent
            anchors.margins: 28
            spacing: 14

            Image {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 68
                Layout.preferredHeight: 68
                source: "file:///usr/share/pixmaps/xodus-app-icon.png"
                fillMode: Image.PreserveAspectFit
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                text: "XODUS"
                font.pixelSize: 18
                font.letterSpacing: 6
                color: "#DBCCF5"
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("Welcome back")
                font.pixelSize: 26
                font.weight: Font.DemiBold
            }

            ComboBox {
                id: account
                objectName: "accountSelector"
                Layout.fillWidth: true
                visible: userModel.count > 0 && !root.manualAccount
                model: userModel
                textRole: "name"
                currentIndex: Math.max(0, userModel.lastIndex)
                enabled: !root.authenticating
                palette.button: "#241B2F"
                palette.buttonText: "#F6F2FF"
                palette.dark: "#D7BEFF"
                Accessible.name: qsTr("Account")
                onActivated: username.text = currentText
                Component.onCompleted: username.text = currentText
            }
            TextField {
                id: username
                objectName: "usernameField"
                Layout.fillWidth: true
                visible: root.manualAccount || userModel.count === 0
                placeholderText: qsTr("Username")
                enabled: !root.authenticating
                selectByMouse: true
                inputMethodHints: Qt.ImhNoAutoUppercase | Qt.ImhNoPredictiveText
                Accessible.name: qsTr("Username")
                onAccepted: password.forceActiveFocus()
            }
            ToolButton {
                objectName: "otherAccountButton"
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredHeight: 26
                visible: userModel.count > 0
                enabled: !root.authenticating
                palette.button: "#241B2F"
                palette.buttonText: "#D7BEFF"
                text: root.manualAccount ? qsTr("Choose an account") : qsTr("Use another account")
                onClicked: {
                    root.manualAccount = !root.manualAccount
                    if (root.manualAccount) {
                        username.text = ""
                        username.forceActiveFocus()
                    } else {
                        username.text = account.currentText
                        password.forceActiveFocus()
                    }
                }
            }
            TextField {
                id: password
                objectName: "passwordField"
                Layout.fillWidth: true
                placeholderText: qsTr("Password")
                echoMode: TextInput.Password
                enabled: !root.authenticating
                selectByMouse: true
                placeholderTextColor: "#AAA0B7"
                focus: true
                inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText
                Accessible.name: qsTr("Password")
                onAccepted: root.signIn()
            }
            Label {
                Layout.fillWidth: true
                visible: keyboard.capsLock
                text: qsTr("Caps Lock is on")
                color: "#D7BEFF"
                font.pixelSize: 12
            }
            Button {
                objectName: "signInButton"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                text: root.authenticating ? qsTr("Signing in…") : qsTr("Sign in")
                enabled: !root.authenticating && username.text.trim().length > 0
                onClicked: root.signIn()
            }
            ComboBox {
                id: session
                objectName: "sessionSelector"
                Layout.fillWidth: true
                model: sessionModel
                textRole: "name"
                currentIndex: Math.max(0, sessionModel.lastIndex)
                enabled: !root.authenticating
                palette.button: "#241B2F"
                palette.buttonText: "#F6F2FF"
                palette.dark: "#D7BEFF"
                Accessible.name: qsTr("Desktop session")
            }
            Label {
                objectName: "loginStatus"
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                text: root.loginMessage
                color: "#E0C8FF"
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                Accessible.role: Accessible.AlertMessage
            }
        }
    }

    RowLayout {
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: 16
        spacing: 16
        Button {
            objectName: "restartButton"
            text: qsTr("Restart")
            flat: true
            visible: sddm.canReboot
            enabled: !root.authenticating
            onClicked: sddm.reboot()
        }
        Button {
            objectName: "powerOffButton"
            text: qsTr("Shut down")
            flat: true
            visible: sddm.canPowerOff
            enabled: !root.authenticating
            onClicked: sddm.powerOff()
        }
    }
}

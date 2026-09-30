// Copyright 2026 Xodus contributors. SPDX-License-Identifier: MIT
import QtQuick 2.15

Item {
    id: root
    width: parent ? parent.width : 1920
    height: parent ? parent.height : 1080
    property int stage: 0

    Image {
        anchors.fill: parent
        source: "file:///usr/share/wallpapers/Xodus/xodus-wallpaper.png"
        fillMode: Image.PreserveAspectCrop
    }

    Rectangle {
        anchors.fill: parent
        color: "#aa070810"
    }

    Column {
        anchors.centerIn: parent
        spacing: 18

        Image {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 120
            height: 120
            source: "file:///usr/share/pixmaps/xodus-app-icon.png"
            fillMode: Image.PreserveAspectFit
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "XODUS"
            color: "#F7F5FF"
            font.family: "Noto Sans"
            font.pixelSize: 32
            font.weight: Font.Medium
            font.letterSpacing: 8
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Preparing your desktop"
            color: "#CFC9DB"
            font.family: "Noto Sans"
            font.pixelSize: 14
        }

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 280
            height: 4
            radius: 2
            color: "#393244"

            Rectangle {
                objectName: "progressFill"
                height: parent.height
                radius: parent.radius
                color: "#B596FF"
                width: parent.width * Math.min(1, Math.max(0, (root.stage - 1) / 5))
                Behavior on width {
                    NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
                }
            }
        }
    }
}

// SPDX-License-Identifier: GPL-2.0-or-later
// Original Xodus frame and task artwork; compatible with the PearDock backend.
import QtQuick
QtObject {
    property string image: "frame.png"
    property string imageTop: "frame.png"
    property string imageBottom: "frame.png"
    property string imageLeft: "frame.png"
    property string imageRight: "frame.png"
    property string imagetask: "tasks.svg"
    property bool blur: true
    property int blurRadius: 24
    property bool liquidGelEffect: true
    property real refractionStrength: 8.0
    property real rgbFringing: 2.0
    property int positionTaskIndicator: 3
    property int leftMargin: 20
    property int topMargin: 20
    property int rightMargin: 20
    property int bottomMargin: 20
    property int outsideLeftMargin: 20
    property int outsideTopMargin: 0
    property int outsideRightMargin: 20
    property int outsideBottomMargin: -10
}

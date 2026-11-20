// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
ComboBox {
    id: chooser
    property string selectedSkin: "Xodus Dark"
    signal skinSelected(string skin)
    model: ["Xodus Dark", "Xodus Light"]
    function syncSelection() { currentIndex = selectedSkin === "Xodus Light" ? 1 : 0 }
    onSelectedSkinChanged: syncSelection()
    Component.onCompleted: syncSelection()
    Accessible.name: "Dock appearance"
    onActivated: index => skinSelected(model[index])
}

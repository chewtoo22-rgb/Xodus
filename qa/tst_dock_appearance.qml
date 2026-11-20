// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtTest
import "../overlay/identity/dock/ui" as DockUI

Rectangle {
    width: 900; height: 760
    color: "#131019"
    TestCase {
        id: tests
        name: "XodusDockAppearance"
        when: windowShown

        function test_frame_assets_data() {
            return [{tag: "light", name: "Xodus Light"}, {tag: "dark", name: "Xodus Dark"}]
        }
        function test_frame_assets(data) {
            const folder = Qt.resolvedUrl("../overlay/identity/dock/skins/" + data.name + "/").toString()
            const component = Qt.createComponent(folder + "Config.qml")
            compare(component.status, Component.Ready, component.errorString())
            const config = component.createObject(tests)
            verify(config !== null)
            compare(config.imagetask, "tasks.svg")
            verify(SvgAudit.checkTasks(decodeURIComponent((folder + config.imagetask).replace("file://", ""))))
            for (const edge of ["imageTop", "imageBottom", "imageLeft", "imageRight"]) {
                frame.source = folder + config[edge]
                tryCompare(frame, "status", Image.Ready)
                waitForRendering(frame)
                const image = grabImage(frame)
                verify(image.width > 0)
                verify(image.alpha(180, 36) > 0)
                if (data.tag === "dark") verify(image.red(180, 65) < 80)
                else verify(image.red(180, 65) > 220)
            }
            const render = grabImage(dockPreview)
            render.save(XodusRenderDirectory + "/dock-" + data.tag + ".png")
            config.destroy()
        }
        function test_selector_signal_and_binding() {
            compare(selector.count, 2)
            selector.selectedSkin = "Xodus Dark"
            compare(selector.currentText, "Xodus Dark")
            selector.forceActiveFocus()
            keyClick(Qt.Key_Down)
            compare(selector.currentText, "Xodus Light")
            compare(selectorSpy.count, 1)
            compare(selectorSpy.signalArguments[0][0], "Xodus Light")
            selector.selectedSkin = "Xodus Dark"
            compare(selector.currentText, "Xodus Dark")
        }
        function test_settings_buttons_and_automatic_schedule() {
            pageLoader.source = XodusSettingsPage
            tryCompare(pageLoader, "status", Loader.Ready)
            const page = pageLoader.item
            const light = findChild(page, "appearance-light")
            const dark = findChild(page, "appearance-dark")
            const automatic = findChild(page, "appearance-auto")
            verify(light && dark && automatic)
            const writes = Dock.writes
            mouseClick(light)
            compare(Appearance.colorScheme, "light")
            compare(Dock.skinName, "Xodus Light")
            verify(light.checked)
            dark.forceActiveFocus()
            keyClick(Qt.Key_Space)
            compare(Appearance.colorScheme, "dark")
            compare(Dock.skinName, "Xodus Dark")
            verify(dark.checked)
            mouseClick(automatic)
            compare(Appearance.colorScheme, "auto")
            compare(Dock.skinName, page.automaticDockSkin(new Date().getHours()))
            compare(page.automaticDockSkin(7), "Xodus Dark")
            compare(page.automaticDockSkin(8), "Xodus Light")
            compare(page.automaticDockSkin(17), "Xodus Light")
            compare(page.automaticDockSkin(18), "Xodus Dark")
            compare(Dock.writes, writes + 3)
            verify(SvgAudit.emitColorScheme(Qt.ColorScheme.Light))
            tryCompare(Dock, "skinName", "Xodus Light")
            verify(SvgAudit.emitColorScheme(Qt.ColorScheme.Dark))
            tryCompare(Dock, "skinName", "Xodus Dark")
            compare(Appearance.colorScheme, "auto")
            grabImage(pageLoader).save(XodusRenderDirectory + "/settings-appearance.png")
        }
    }
    Rectangle {
        id: dockPreview
        width: 540; height: 130
        color: "#5c397b"
        visible: pageLoader.status !== Loader.Ready
        BorderImage {
            id: frame
            x: 70; y: 25; width: 400; height: 74
            border { left: 20; right: 20; top: 20; bottom: 20 }
            horizontalTileMode: BorderImage.Stretch
            verticalTileMode: BorderImage.Stretch
            Row {
                anchors.centerIn: parent; spacing: 14
                Repeater {
                    model: ["#9b6bdb", "#edaa6a", "#79b9bb", "#cfbadf", "#9165c9"]
                    delegate: Rectangle {
                        required property color modelData
                        width: 42; height: 42; radius: 10; color: modelData
                        Rectangle { anchors.centerIn: parent; width: 14; height: 14; radius: 4; color: "#f9f6ff" }
                    }
                }
            }
        }
    }
    DockUI.XodusSkinSelector {
        id: selector; y: 150; visible: pageLoader.status !== Loader.Ready
        onSkinSelected: skin => selectedSkin = skin
    }
    SignalSpy { id: selectorSpy; target: selector; signalName: "skinSelected" }
    Loader { id: pageLoader; y: 0; width: 680; height: 740 }
}

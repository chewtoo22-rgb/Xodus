// SPDX-License-Identifier: GPL-2.0-or-later
// Qt6 acceptance uses the real QML controls with disposable backend objects.
#include <QtQuickTest/quicktest.h>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QSvgRenderer>
#include <QImage>
#include <QPainter>
#include <QGuiApplication>
#include <QStyleHints>

class SvgAudit : public QObject {
    Q_OBJECT
public:
    using QObject::QObject;
    Q_INVOKABLE bool emitColorScheme(int scheme) {
        // The offscreen platform has no desktop theme provider. Deliver its
        // documented Qt signal to exercise the real page's Connections.
        return QMetaObject::invokeMethod(QGuiApplication::styleHints(), "colorSchemeChanged",
            Qt::DirectConnection, Q_ARG(Qt::ColorScheme, static_cast<Qt::ColorScheme>(scheme)));
    }
    Q_INVOKABLE bool checkTasks(const QString &path) {
        QSvgRenderer svg(path);
        if (!svg.isValid()) return false;
        const QStringList states = {"normal", "minimized", "focus", "hover", "attention", "progress", "launcher", "launcher-hover"};
        const QStringList edges = {"", "north-", "south-", "west-", "east-"};
        const QStringList parts = {"center", "top", "bottom", "left", "right", "topleft", "topright", "bottomleft", "bottomright"};
        for (const auto &edge : edges)
            for (const auto &state : states)
                for (const auto &part : parts)
                    if (!svg.elementExists(edge + state + "-" + part)) return false;
        // Render the actual task hover/focus elements, not a stand-in image.
        QImage image(160, 40, QImage::Format_ARGB32_Premultiplied);
        image.fill(Qt::transparent);
        QPainter painter(&image);
        for (int i = 0; i < edges.size(); ++i)
            svg.render(&painter, edges[i] + "focus-center", QRectF(i * 32, 0, 28, 28));
        painter.end();
        for (int i = 0; i < edges.size(); ++i)
            if (qAlpha(image.pixel(i * 32 + 14, 14)) == 0) return false;
        return true;
    }
};

class DockSetup : public QObject {
    Q_OBJECT
public slots:
    void qmlEngineAvailable(QQmlEngine *engine) {
        auto object = [engine](const QByteArray &body) {
            QQmlComponent component(engine);
            component.setData("import QtQuick\nQtObject {" + body + "}", QUrl());
            QObject *value = component.create();
            if (!value) qFatal("Mock backend failed to load");
            value->setParent(engine);
            return value;
        };
        engine->rootContext()->setContextProperty("Appearance", object(R"(
            property string colorScheme: "dark"
            property string accent: "purple"
            property bool tintEnabled: false
            property real animationSpeed: 1
            property bool lgEnabled: true
            property int lgBlurStrength: 8
            property int lgNoiseStrength: 0
            property int lgRefractionStrength: 8
            property int lgRefractionEdgeSize: 20
            property int lgRGBFringing: 2
            property int selections: 0
            function refresh() {}
            function setColorScheme(mode) { colorScheme = mode; selections++ }
            function setAccent(value) { accent = value }
            function setAnimationSpeed(value) { animationSpeed = value }
            function setTintEnabled(value) { tintEnabled = value }
            function setLgEnabled(value) { lgEnabled = value }
            function setLgBlurStrength(value) { lgBlurStrength = value }
            function setLgNoiseStrength(value) { lgNoiseStrength = value }
            function setLgRefractionStrength(value) { lgRefractionStrength = value }
            function setLgRefractionEdgeSize(value) { lgRefractionEdgeSize = value }
            function setLgRGBFringing(value) { lgRGBFringing = value }
        )"));
        engine->rootContext()->setContextProperty("Dock", object(R"(
            property string skinName: "Xodus Dark"
            property int writes: 0
            function set(key, value) { if (key === "skinName") { skinName = value; writes++ } }
        )"));
        engine->rootContext()->setContextProperty("Scrollbars", object(R"(
            property bool alwaysVisible: false
            property bool clickToJump: false
            function refresh() {}
            function setAlwaysVisible(value) { alwaysVisible = value }
            function setClickToJump(value) { clickToJump = value }
        )"));
        engine->rootContext()->setContextProperty("FilerConfig", object(R"(
            property var groups: []
            function refresh() {}
            function setValue(group, key, value) {}
        )"));
        engine->rootContext()->setContextProperty("SvgAudit", new SvgAudit(engine));
        engine->rootContext()->setContextProperty("XodusSettingsPage", QUrl::fromLocalFile(qEnvironmentVariable("XODUS_SETTINGS_PAGE")));
        engine->rootContext()->setContextProperty("XodusRenderDirectory", qEnvironmentVariable("XODUS_RENDER_DIRECTORY"));
    }
};

QUICK_TEST_MAIN_WITH_SETUP(xodus_dock, DockSetup)
#include "dock-render-acceptance.moc"

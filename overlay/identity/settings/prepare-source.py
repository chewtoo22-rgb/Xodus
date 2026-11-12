#!/usr/bin/env python3
"""Prepare the audited Qt6 Settings source before compiling a Xodus executable."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def replace_once(text, before, after, label):
    if text.count(before) != 1:
        raise SystemExit(f"Settings source layout changed: {label}")
    return text.replace(before, after, 1)


def prepare(vendor, destination, overlay):
    lock = json.loads((overlay / "source.lock.json").read_text(encoding="utf-8"))
    def git(*args):
        return subprocess.check_output(["git", "-C", str(vendor), *args], text=True).strip()
    if git("rev-parse", "HEAD") != lock["commit"]:
        raise SystemExit("Settings source commit differs from source.lock.json")
    if git("rev-parse", "HEAD:pearos-settings-app") != lock["settings_tree"]:
        raise SystemExit("Settings source tree differs from source.lock.json")
    if subprocess.run(["git", "-C", str(vendor), "diff", "--quiet", "HEAD", "--", "pearos-settings-app"]).returncode:
        raise SystemExit("Settings vendor source contains changes")
    if git("ls-files", "--others", "--exclude-standard", "pearos-settings-app"):
        raise SystemExit("Settings vendor source contains untracked files")
    source = vendor / "pearos-settings-app"
    if any(p.is_symlink() and "assets" not in p.relative_to(source).parts for p in source.rglob("*")):
        raise SystemExit("Settings source contains an unexpected symlink")
    if destination.exists() or destination.is_symlink():
        raise SystemExit("Settings output already exists")

    # Validate the complete patch before writing any prepared source.
    cmake = (source / "CMakeLists.txt").read_text(encoding="utf-8")
    cmake = replace_once(cmake, "URI PearOSSettings", "URI XodusSettings", "QML module")
    for filename in ("backend/pearidmanager.cpp", "backend/pirimanager.cpp", "backend/sidereflection.cpp",
                     "qml/pages/PearIDPage.qml", "qml/pages/PearIntelligencePage.qml"):
        cmake = replace_once(cmake, "    " + filename + "\n", "", filename)
    main = (source / "main.cpp").read_text(encoding="utf-8")
    for filename in ("pearidmanager", "pirimanager", "sidereflection"):
        main = replace_once(main, '#include "backend/' + filename + '.h"\n', "", filename)
    for line in ('    PearIDManager    pearid;\n', '    PiriManager      piri;\n',
                 '    SidebarReflection* siderefl = new SidebarReflection();\n',
                 '    engine.addImageProvider("siderefl", new SidebarReflectionProvider(siderefl));\n',
                 '    ctx->setContextProperty("PearID",     &pearid);\n',
                 '    ctx->setContextProperty("SidebarRefl", siderefl);\n',
                 '    ctx->setContextProperty("Piri",       &piri);\n'):
        main = replace_once(main, line, "", line.strip())
    main = replace_once(main, '    qputenv("QT_QPA_PLATFORM", "xcb");',
                        '    // Honor the desktop platform and the offscreen build acceptance check.', "platform")
    main = replace_once(main, 'setOrganizationName("PearOS")', 'setOrganizationName("Xodus")', "organization")
    main = replace_once(main, 'setApplicationName("systemsettings1")', 'setApplicationName("xodus-settings")', "application")
    # Dock pins and the installed .desktop launcher retain this stable internal
    # ID. App name and StartupWMClass carry the visible Xodus identity.
    if main.count('setDesktopFileName("pearos-systemsettings")') != 1:
        raise SystemExit("Settings source layout changed: desktop ID")
    main = replace_once(main, '    engine.loadFromModule("PearOSSettings", "Main");',
        '''    ctx->setContextProperty("XodusInitialPage", app.arguments().contains("--about") ? 28 :
                            app.arguments().contains("--appearance") ? 6 : 4);
    engine.loadFromModule("XodusSettings", "Main");''', "entrypoint")
    main = replace_once(main, '#include <QGuiApplication>', '#include <QGuiApplication>\n#include <QTimer>\n#include <QImage>', "test includes")
    main = replace_once(main, '    return app.exec();', '''    if (app.arguments().contains("--self-test")) {
        QTimer::singleShot(1200, &app, [&]() {
            auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
            const QImage frame = window ? window->grabWindow() : QImage();
            const QString output = qEnvironmentVariable("XODUS_SETTINGS_RENDER_PATH");
            if (frame.isNull() || (!output.isEmpty() && !frame.save(output, "PNG"))) {
                qCritical("Xodus Settings could not render its QML window");
                app.exit(70);
                return;
            }
            app.exit(0);
        });
    }
    return app.exec();''', "render acceptance")
    replacements = {
        "qml/pages/SoftwareUpdatePage.qml": [('SysInfo.osName || "pearOS"', 'SysInfo.osName || "Xodus"')],
        "qml/pages/PrivacyPage.qml": [('"Media & Pear Music"', '"Media Players"')],
        "qml/pages/AppearancePage.qml": [( 'img: ap + "' + name + '.png"', 'img: "file:///usr/share/wallpapers/Xodus/xodus-wallpaper.png"') for name in ("auto", "light", "dark")],
    }
    changed = {}
    for relative, edits in replacements.items():
        text = (source / relative).read_text(encoding="utf-8")
        for before, after in edits:
            text = replace_once(text, before, after, relative)
        changed[relative] = text
    # These normalized text hashes are the audited Git blob bytes, independent
    # of a Windows checkout's CRLF conversion. All nonappearance APIs remain.
    appearance_inputs = {
        "backend/dockmanager.cpp": "0a411b3526d3e691c1f3f5a604fbef92c71edf5696304232d8f9f7f575069cc9",
        "backend/dockmanager.h": "9858da385db9283f9811972f44d62c0c38c1efe3dc7b6e818bf16d03fc7ccec8",
        "backend/appearancemanager.cpp": "7cf8c792e9ab8bb240e9de864dce53df9e2c576e299390848da36f5fcd811cec",
        "qml/pages/AppearancePage.qml": "673fb931632bbe82421a1cefda3e8c6f1a7bb5fe546669ea32da4df5dc74790d",
    }
    for relative, sha in appearance_inputs.items():
        if hashlib.sha256((source / relative).read_text(encoding="utf-8").encode()).hexdigest() != sha:
            raise SystemExit("Settings appearance source differs: " + relative)
    dock = (source / "backend/dockmanager.cpp").read_text(encoding="utf-8")
    dock = replace_once(dock,
        '''    for (const QFileInfo &fi : skinsDir.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot))
        m_availableSkins.append(fi.fileName());
    if (m_availableSkins.isEmpty())
        m_availableSkins = {"Tahoe Dark", "Tahoe", "Big Sur Light", "Big Sur Night"};''',
        '''    for (const QFileInfo &fi : skinsDir.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot)) {
        if (fi.fileName() == "Xodus Dark" || fi.fileName() == "Xodus Light")
            m_availableSkins.append(fi.fileName());
    }
    if (m_availableSkins.isEmpty())
        m_availableSkins = {"Xodus Dark", "Xodus Light"};''', "dock skin list")
    dock = replace_once(dock, '    m_skinName      = readKey("skinName",    "Tahoe Dark");',
        '''    m_skinName      = readKey("skinName",    "Xodus Dark");
    if (!m_availableSkins.contains(m_skinName)) m_skinName = "Xodus Dark";''', "dock read default")
    dock = replace_once(dock, 'void DockManager::set(const QString &key, const QVariant &value) {',
        '''void DockManager::set(const QString &key, const QVariant &value) {
    if (key == "skinName" && !m_availableSkins.contains(value.toString())) return;''', "dock write guard")
    changed["backend/dockmanager.cpp"] = dock
    changed["backend/dockmanager.h"] = replace_once((source / "backend/dockmanager.h").read_text(encoding="utf-8"),
        'QString m_skinName   = "Tahoe Dark";', 'QString m_skinName   = "Xodus Dark";', "dock initial state")
    # Service IDs and installed theme paths stay compatible with the packages;
    # the description displayed by systemctl belongs to the Xodus identity.
    for relative in ("backend/appearancemanager.cpp", "backend/screentimemanager.cpp"):
        text = (source / relative).read_text(encoding="utf-8")
        changed[relative] = text.replace("Description=PearOS ", "Description=Xodus ")
    appearance = changed["backend/appearancemanager.cpp"]
    start = appearance.index("    // Map accent preset names to available pearOS icon theme variants\n")
    end = appearance.index("    m_iconTheme = theme;\n", start)
    appearance = replace_once(appearance, appearance[start:end], '''    // Accent colors still use the existing KDE accent API. The icon family
    // stays Breeze rather than selecting a distribution-branded variant.
    Q_UNUSED(accent);
    const bool dark = colorScheme == "dark" || (colorScheme == "auto" &&
        (QTime::currentTime().hour() < 8 || QTime::currentTime().hour() >= 18));
    const QString theme = dark ? "breeze-dark" : "breeze";

''', "accent icon family")
    changed["backend/appearancemanager.cpp"] = appearance
    # Asset files are provided by the installed package; several unused icon
    # aliases in this source tree point outside its directory. Do not follow
    # those links while preparing the compile inputs.
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("assets"))
    (destination / "assets").mkdir()
    for relative, text in {"CMakeLists.txt": cmake, "main.cpp": main, **changed}.items():
        (destination / relative).write_text(text, newline="\n")
    for item in (overlay / "qml").rglob("*.qml"):
        target = destination / "qml" / item.relative_to(overlay / "qml")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.read_text(encoding="utf-8"), newline="\n")
    # These pages advertise upstream cloud services, and are outside the Xodus
    # settings surface. They are not compiled or reachable from navigation.
    for filename in ("PearIDPage.qml", "PearIntelligencePage.qml"):
        (destination / "qml/pages" / filename).unlink()
    print("Xodus Settings source prepared from " + lock["commit"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendor", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    prepare(args.vendor, args.destination, Path(__file__).resolve().parent)

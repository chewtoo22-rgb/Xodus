#!/usr/bin/env python3
"""Prepare the audited Qt6 Settings source before compiling a Xodus executable."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess


def replace_once(text, before, after, label):
    if text.count(before) != 1:
        raise SystemExit(f"Settings source layout changed: {label}")
    return text.replace(before, after, 1)


def prepare(vendor, destination, overlay):
    lock = json.loads((overlay / "source.lock.json").read_text())
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
    cmake = (source / "CMakeLists.txt").read_text()
    cmake = replace_once(cmake, "URI PearOSSettings", "URI XodusSettings", "QML module")
    for filename in ("backend/pearidmanager.cpp", "backend/pirimanager.cpp", "backend/sidereflection.cpp",
                     "qml/pages/PearIDPage.qml", "qml/pages/PearIntelligencePage.qml"):
        cmake = replace_once(cmake, "    " + filename + "\n", "", filename)
    main = (source / "main.cpp").read_text()
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
        '''    ctx->setContextProperty("XodusInitialPage", app.arguments().contains("--about") ? 28 : 4);
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
        text = (source / relative).read_text()
        for before, after in edits:
            text = replace_once(text, before, after, relative)
        changed[relative] = text
    # Service IDs and installed theme paths stay compatible with the packages;
    # the description displayed by systemctl belongs to the Xodus identity.
    for relative in ("backend/appearancemanager.cpp", "backend/screentimemanager.cpp"):
        text = (source / relative).read_text()
        changed[relative] = text.replace("Description=PearOS ", "Description=Xodus ")
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
        target.write_text(item.read_text(), newline="\n")
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

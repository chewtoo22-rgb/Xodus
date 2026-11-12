#!/usr/bin/env python3
"""Apply or verify original Xodus dock artwork against the audited package."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

CONTENTS = Path("usr/share/plasma/plasmoids/PearDock/contents")
LICENSES = Path("usr/share/licenses/xodus-dock")
REPORT = Path("usr/lib/xodus/dock-source.json")
SKINS = ("Xodus Dark", "Xodus Light")
OLD_SKINS = ("Big Sur Light", "Big Sur Night", "Tahoe", "Tahoe Dark")
PAYLOAD = Path(__file__).resolve().parent
SCAN_DIRS = ((CONTENTS / "skins").as_posix(),)
ABSENT_PATHS = tuple((CONTENTS / "skins" / p).as_posix() for p in (*OLD_SKINS, "readme"))
USER_CONFIGS = ("etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc",
                "home/liveuser/.config/plasma-org.kde.plasma.desktop-appletsrc")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked(root, relative):
    """Reject links rather than following guest paths into the build host."""
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise SystemExit(f"Dock path contains a symlink: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise SystemExit(f"Dock path escapes live root: {relative}")
    return path


def replace_once(text, before, after, label):
    if text.count(before) != 1:
        raise SystemExit(f"Dock source layout changed: {label}")
    return text.replace(before, after, 1)


def patches(source):
    main = replace_once(source["ui/main.qml"],
        '      let skinName = Plasmoid.configuration.skinName || "Tahoe Dark";',
        '''      let skinName = Plasmoid.configuration.skinName || "Xodus Dark";
      // Accept only the original Xodus runtime skins.
      if (skinName !== "Xodus Light" && skinName !== "Xodus Dark") {
          skinName = "Xodus Dark";
      }''', "runtime skin default")
    config = source["ui/ConfigAppearance.qml"]
    config = replace_once(config,
        "import Qt.labs.folderlistmodel // Importante para listar las carpetas de skins\n", "", "skin model import")
    start = config.index("        // ComboBox para mostrar los skins\n")
    end = config.index("        // --- Selector de Tamaño de Iconos ---\n", start)
    config = config[:start] + '''        XodusSkinSelector {
            id: skinChooser
            Kirigami.FormData.label: "Appearance:"
            selectedSkin: root.cfg_skinName
            onSkinSelected: skin => root.cfg_skinName = skin
        }
''' + config[end:]
    xml = replace_once(source["config/main.xml"], "<default>Tahoe Dark</default>",
                       "<default>Xodus Dark</default>", "configuration default")
    return {"ui/main.qml": main.encode(), "ui/ConfigAppearance.qml": config.encode(), "config/main.xml": xml.encode()}


def asset_files(overlay):
    # Repo text is canonical LF even when a host checkout uses CRLF. Package
    # source checks and PNG hashes still bind their exact original bytes.
    def contents(path):
        return path.read_bytes() if path.suffix == ".png" else path.read_text(encoding="utf-8").encode()
    files = {CONTENTS / "skins" / p.relative_to(overlay / "skins"): contents(p)
             for p in sorted((overlay / "skins").rglob("*")) if p.is_file()}
    files[CONTENTS / "ui/XodusSkinSelector.qml"] = contents(overlay / "ui/XodusSkinSelector.qml")
    files[LICENSES / "NOTICE"] = contents(overlay / "NOTICE")
    return files


def migrate_config(data):
    mapping = {"Big Sur Light": "Xodus Light", "Tahoe": "Xodus Light",
               "Big Sur Night": "Xodus Dark", "Tahoe Dark": "Xodus Dark"}
    def convert(match):
        value = match[2]
        if value not in (*SKINS, *OLD_SKINS):
            raise SystemExit(f"Unreviewed dock skin preference: {value}")
        return match[1] + mapping.get(value, value)
    return re.sub(r"^(skinName\s*=\s*)([^\r\n]+)$", convert, data, flags=re.MULTILINE)


def installed_files(overlay, lock):
    return sorted(str(p).replace("\\", "/") for p in (
        *asset_files(overlay), *(CONTENTS / p for p in lock["source_files"]),
        *(LICENSES / "upstream-skins" / p for p in lock["upstream_skin_files"]), REPORT))


def verify(root, payload=PAYLOAD, lock=None):
    root, overlay = Path(root), Path(payload)
    lock = lock or json.loads((overlay / "source.lock.json").read_text(encoding="utf-8"))
    report = json.loads(checked(root, REPORT).read_text(encoding="utf-8"))
    expected = {str(p).replace("\\", "/"): digest(data) for p, data in asset_files(overlay).items()}
    expected.update({str(CONTENTS / p).replace("\\", "/"): h for p, h in lock["patched_files"].items()})
    expected.update({str(LICENSES / "upstream-skins" / p).replace("\\", "/"): h
                     for p, h in lock["upstream_skin_files"].items()})
    if report != {"schema": 1, "package": lock["package"], "version": lock["version"],
                  "package_sha256": lock["package_sha256"], "source_files": lock["source_files"],
                  "output_files": expected}:
        raise SystemExit("Dock provenance differs from the reviewed contract")
    skins = checked(root, CONTENTS / "skins")
    if sorted(p.name for p in skins.iterdir()) != sorted(SKINS):
        raise SystemExit("Dock exposes competing or missing runtime skins")
    for relative, sha in expected.items():
        path = checked(root, relative)
        if not path.is_file() or digest(path.read_bytes()) != sha:
            raise SystemExit(f"Dock payload differs: {relative}")
    for relative in USER_CONFIGS:
        path = checked(root, relative)
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if migrate_config(text) != text:
                raise SystemExit(f"Dock retains an upstream skin preference: {relative}")
    return {"schema": 1, "output_files": expected}


def apply(root, overlay, lock):
    if checked(root, REPORT).exists():
        raise SystemExit("Dock identity already applied; use --verify")
    sources = {}
    for relative, sha in lock["source_files"].items():
        path = checked(root, CONTENTS / relative)
        if not path.is_file() or digest(path.read_bytes()) != sha:
            raise SystemExit(f"Dock package input differs: {relative}")
        sources[relative] = path.read_text(encoding="utf-8")
    skinroot = checked(root, CONTENTS / "skins")
    observed = {p.relative_to(skinroot).as_posix() for p in skinroot.rglob("*") if p.is_file() or p.is_symlink()}
    if observed != set(lock["upstream_skin_files"]):
        raise SystemExit("Dock package skin file list differs")
    for relative, sha in lock["upstream_skin_files"].items():
        path = checked(root, CONTENTS / "skins" / relative)
        if not path.is_file() or digest(path.read_bytes()) != sha:
            raise SystemExit(f"Dock package skin differs: {relative}")
    changed = patches(sources)
    if {p: digest(data) for p, data in changed.items()} != lock["patched_files"]:
        raise SystemExit("Dock reviewed patch output differs")
    # Prepare user preference edits before mutating package files. The broad
    # shell identity pass handles other panel settings and launchers.
    prefs = [Path("etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc")]
    homedir = checked(root, "home")
    if homedir.is_dir():
        prefs += [p.relative_to(root) / ".config/plasma-org.kde.plasma.desktop-appletsrc"
                  for p in homedir.iterdir() if p.is_dir()]
    preferences = {}
    for relative in prefs:
        path = checked(root, relative)
        if path.is_file():
            preferences[relative] = migrate_config(path.read_text(encoding="utf-8"))
    archive = checked(root, LICENSES / "upstream-skins")
    if archive.exists():
        raise SystemExit("Dock upstream archive already exists")
    for relative in asset_files(overlay):
        checked(root, relative)
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(skinroot), str(archive))
    for relative, data in {**asset_files(overlay), **{CONTENTS / p: b for p, b in changed.items()}}.items():
        path = checked(root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o644)
    for relative, text in preferences.items():
        checked(root, relative).write_text(text, newline="\n")
    outputs = {str(p).replace("\\", "/"): digest(checked(root, p).read_bytes())
               for p in installed_files(overlay, lock) if p != REPORT.as_posix()}
    report = {"schema": 1, "package": lock["package"], "version": lock["version"],
              "package_sha256": lock["package_sha256"], "source_files": lock["source_files"], "output_files": outputs}
    path = checked(root, REPORT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", newline="\n")
    return verify(root, overlay, lock)


TRANSFER_FILES = tuple(installed_files(PAYLOAD, json.loads((PAYLOAD / "source.lock.json").read_text(encoding="utf-8"))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("live_root", type=Path, nargs="?")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--list-installed-files", action="store_true")
    args = parser.parse_args()
    overlay = Path(__file__).resolve().parent
    lock = json.loads((overlay / "source.lock.json").read_text(encoding="utf-8"))
    if args.list_installed_files:
        print("\n".join(installed_files(overlay, lock)))
    elif args.live_root is None:
        parser.error("live_root is required")
    elif args.verify:
        print(json.dumps(verify(args.live_root.resolve(), overlay, lock), sort_keys=True))
    else:
        print(json.dumps(apply(args.live_root.resolve(), overlay, lock), sort_keys=True))

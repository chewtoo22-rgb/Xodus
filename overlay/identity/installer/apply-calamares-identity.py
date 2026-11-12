#!/usr/bin/env python3
"""Apply Xodus presentation to the audited Calamares package after installation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"Xodus Calamares identity: {message}")


def regular(root: Path, relative: str) -> Path:
    path = root / relative
    require(path.is_file() and not path.is_symlink() and root in path.resolve().parents,
            f"missing or unsafe file: {relative}")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(live_root: Path) -> None:
    live_root = live_root.resolve(strict=True)
    require(live_root != Path(live_root.anchor), "expected staged live root")
    root = live_root / "etc/calamares"
    require(root.is_dir() and not root.is_symlink() and live_root in root.resolve().parents,
            "Calamares package is absent or unsafe")
    manifest = json.loads((HERE / "calamares-source-checksums.json").read_text())
    original = {}
    for name, expected in manifest["files"].items():
        path = regular(root, name)
        content = path.read_bytes().replace(b"\r\n", b"\n")
        require(hashlib.sha256(content).hexdigest() == expected, f"audited package source changed: {name}")
        original[name] = content
    assets = json.loads((HERE / "assets-checksums.json").read_text())
    for name, expected in assets.items():
        require(digest(regular(HERE, name)) == expected, f"reviewed identity asset changed: {name}")
    destination = root / "branding/Xodus"
    require(not destination.exists() and not destination.is_symlink(), "Xodus branding destination already exists")
    require(not (root / "branding").is_symlink(), "branding directory is unsafe")
    record_path = root / "xodus-calamares-identity.json"
    require(not record_path.exists() and not record_path.is_symlink(), "identity record already exists")
    protected = {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*")
                 if p.is_file() and not p.is_symlink() and not p.is_relative_to(root / "branding")
                 and p != root / "settings.conf"}
    settings, count = re.subn(r"(?m)^branding: pearOS$", "branding: Xodus", original["settings.conf"].decode())
    require(count == 1, "branding selector layout changed")
    description = original["branding/pearOS/branding.desc"].decode()
    replacements = {
        "componentName": "Xodus", "productName": "Xodus", "shortProductName": "Xodus",
        "version": "X1 preview", "shortVersion": "X1", "versionedName": "Xodus X1",
        "shortVersionedName": "Xodus X1", "bootloaderEntryName": "Xodus",
        "productLogo": '"xodus-installer-mark.svg"', "productIcon": '"xodus-installer-mark.svg"',
        "productWelcome": '"xodus-installer-mark.svg"', "SidebarBackground": '"#111018"',
        "SidebarText": '"#F5F1FC"', "SidebarTextCurrent": '"#FFFFFF"',
        "SidebarBackgroundCurrent": '"#45324F"',
    }
    for key, value in replacements.items():
        description, count = re.subn(rf"(?m)^(\s*{key}:)\s*[^\n]+$", rf"\1 {value}", description)
        require(count == 1, f"branding field changed: {key}")
    slideshow = original["branding/pearOS/show.qml"].decode()
    require(slideshow.count('source: "slide1.png"') == 1, "slideshow source layout changed")
    slideshow = slideshow.replace('source: "slide1.png"', 'source: "xodus-installer-wallpaper.svg"')
    # All checks complete before changing any staged package file.
    destination.mkdir()
    for name, content in {"branding.desc": description, "show.qml": slideshow}.items():
        (destination / name).write_text(content, encoding="utf-8", newline="\n")
    (destination / "calamares-sidebar.qml").write_bytes(original["branding/pearOS/calamares-sidebar.qml"])
    shutil.copyfile(HERE / "xodus-calamares.qss", destination / "stylesheet.qss")
    for name in ("xodus-installer-mark.svg", "xodus-installer-wallpaper.svg"):
        shutil.copyfile(HERE / "assets" / name, destination / name)
    (root / "settings.conf").write_text(settings, encoding="utf-8", newline="\n")
    require(all(digest(root / name) == sha for name, sha in protected.items()),
            "Calamares install behavior changed")
    record = {"schema": 1, "source_package": f'{manifest["package"]}-{manifest["version"]}',
              "protected": protected, "files": {p.relative_to(root).as_posix(): digest(p)
              for p in destination.iterdir()}, "settings.conf": digest(root / "settings.conf")}
    (root / "xodus-calamares-identity.json").write_text(json.dumps(record, indent=2) + "\n", newline="\n")
    print("Applied Xodus Calamares identity; install module and launch hashes unchanged")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("live_root", type=Path)
    args = parser.parse_args()
    try:
        transform(args.live_root)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

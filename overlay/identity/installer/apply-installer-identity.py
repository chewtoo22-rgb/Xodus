#!/usr/bin/env python3
"""Rebrand the locked installer frontend without changing install behavior."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil


HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "source-checksums.json"
APP_ROOTS = ("system_install/frontend/app", "post-install/app")
SUFFIXES = {".html", ".css", ".json", ".js"}
ICONS = {
    "nicec0re-logo-dark.png": "xodus-installer-mark.svg",
    "nicec0re-logo.png": "xodus-installer-mark.svg",
    "packup-logo.png": "xodus-restore.svg",
    "packup.png": "xodus-restore.svg",
    "disk.png": "xodus-disk.svg",
    "languages-icon.png": "xodus-language.svg",
    "country.png": "xodus-language.svg",
    "keyboard.png": "xodus-keyboard.svg",
    "finish.png": "xodus-finish.svg",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"Xodus installer identity: {message}")


def regular(root: Path, relative: str) -> Path:
    path = root / relative
    require(path.is_file() and not path.is_symlink() and root in path.resolve().parents,
            f"missing or unsafe source file: {relative}")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(path: Path) -> bytes:
    # Native Windows Git checkouts can convert LF source to CRLF. Compare the
    # original Git text representation while preserving every backend byte.
    return path.read_bytes().replace(b"\r\n", b"\n")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def visible_text(content: str) -> str:
    return (content.replace("pearOS NiceCC0re", "Xodus").replace("pearOS NiceC0re", "Xodus")
            .replace("pearOS", "Xodus").replace("pear OS", "Xodus"))


def references(content: str) -> str:
    for old, new in ICONS.items():
        content = content.replace(old, new)
    return content


def patch_disk_selection(content: str) -> str:
    # The pinned page calls showEraseModal(), so the old controller could
    # never find its Continue control. Keep every confirmation/backend action
    # intact and disable this control until a real disk entry is selected.
    old = "allButtons[j].getAttribute('onclick').includes('select_disk')"
    require(content.count(old) == 1, "disk Continue selector layout changed")
    result = content.replace(old, "(allButtons[j].getAttribute('onclick').includes('select_disk') || "
                             "allButtons[j].getAttribute('onclick').includes('showEraseModal'))")
    old = "if (!hasSelection || (selectedDisk && (selectedDisk.value === '/dev/null'"
    require(result.count(old) == 1, "disk selection guard layout changed")
    return result.replace(old, "if (!hasSelection || !selectedDisk || !selectedDisk.value || "
                          "(selectedDisk && (selectedDisk.value === '/dev/null'")


def patch_html(content: str, relative: str, root: Path) -> str:
    result = references(visible_text(content))
    # Keep the full original legal terms and attribution in the source. This
    # footer describes retained component licenses without inventing a Xodus
    # software agreement or presenting upstream branding as the product name.
    result = re.sub(r'<p[^>]*class="license-sub-text"[^>]*>.*?https://pearos\.xyz/legal/license.*?</p>',
                    '<p class="license-sub-text">Components retain their own licenses. Upstream attribution is retained with the installer source.</p>',
                    result, flags=re.S)
    app = next(app for app in APP_ROOTS if relative.startswith(app + "/"))
    css = os.path.relpath(root / app / "css/xodus-installer.css", (root / relative).parent).replace("\\", "/")
    if not relative.endswith("resources/navbar.html"):
        require(content.count("</head>") == 1, f"HTML head layout changed: {relative}")
        result = result.replace("</head>", f'  <link rel="stylesheet" href="{css}">\n</head>')
    if relative == "post-install/app/hello.html":
        result, count = re.subn(r'<svg class="hello__svg".*?</svg>',
                               '<img class="xodus-setup-mark" src="resources/xodus-installer-mark.svg" alt="Xodus">\n'
                               '      <h1>Welcome to Xodus</h1>\n'
                               '      <p class="setup-text">Make this space your own.</p>', result, count=1, flags=re.S)
        require(count == 1, "post-install greeting layout changed")
    return result


def patch_navbar(content: str, mark: str) -> str:
    result = visible_text(content)
    result, count = re.subn(r'src="data:image/svg\+xml;base64,[A-Za-z0-9+/=]+"',
                           f'src="data:image/svg+xml;base64,{mark}"', result)
    require(count == 1, "navbar embedded logo count changed")
    result = result.replace('<p><strong>Author:</strong> Pear Software and Services</p>',
                            '<p><strong>Interface:</strong> Xodus Project</p>')
    result = result.replace('<p><strong>Email:</strong> alex@pear-software.com</p>',
                            '<p><strong>Foundation:</strong> Upstream attribution retained in the installer source.</p>')
    return result


def transform(root: Path) -> list[str]:
    root = root.resolve(strict=True)
    require(root != Path(root.anchor), "expected installer checkout root")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    original = {}
    protected_before = {}
    # Validate every frontend and protected backend byte before writing. This
    # also rejects a build that tries to apply identity after backend patches.
    for group in ("frontend", "protected"):
        for relative, expected in manifest[group].items():
            path = regular(root, relative)
            require(hashlib.sha256(canonical(path)).hexdigest() == expected, f"locked source checksum changed: {relative}")
            original[relative] = canonical(path)
            if group == "protected":
                protected_before[relative] = digest(path)
    actual = {path.relative_to(root).as_posix() for app in APP_ROOTS for path in (root / app).rglob("*")
              if path.is_file() and path.suffix in SUFFIXES}
    require(actual == set(manifest["frontend"]), "frontend file inventory changed")
    setup = original["system_install/setup"]
    blob = hashlib.sha1(f"blob {len(setup)}\0".encode() + setup).hexdigest()
    require(blob == manifest["setup_blob"], "installer setup blob no longer matches the lock")
    for app in APP_ROOTS:
        for relative in (app, app + "/css", app + "/resources"):
            path = root / relative
            require(path.is_dir() and not path.is_symlink() and root in path.resolve().parents,
                    f"unsafe frontend output directory: {relative}")
    for relative in ("xodus-upstream-notices", "xodus-frontend-identity.json"):
        path = root / relative
        require(not path.exists() and not path.is_symlink(), f"identity output already exists: {relative}")
    assets = json.loads((HERE / "assets-checksums.json").read_text())
    for name, expected in assets.items():
        require(digest(regular(HERE, name)) == expected, f"reviewed identity asset changed: {name}")
    for app in APP_ROOTS:
        for name in assets:
            if name.startswith("assets/"):
                target = root / app / "resources" / Path(name).name
                require(not target.is_symlink(), f"unsafe asset destination: {target}")
    mark = base64.b64encode((HERE / "assets/xodus-installer-mark.svg").read_bytes()).decode("ascii")
    updates = {}
    for relative in manifest["frontend"]:
        content = original[relative].decode("utf-8-sig")
        result = content
        if relative.endswith(".html"):
            if relative.startswith(("post-install/app/aa/", "post-install/app/resources/")):
                # Unused design demos are retained as upstream source. Active
                # finish.html loads their CSS/JS, overridden by our stylesheet.
                continue
            result = patch_html(content, relative, root)
            if relative.endswith("resources/navbar.html"):
                result, count = re.subn(r'src="data:image/svg\+xml;base64,[A-Za-z0-9+/=]+"',
                                       f'src="data:image/svg+xml;base64,{mark}"', result)
                require(count == 1, "static recovery navbar logo count changed")
        elif relative.startswith("post-install/app/i18n/") and relative.endswith(".json"):
            result = visible_text(content)
            require(json.loads(content).keys() == json.loads(result).keys(), "translation keys changed")
        elif relative == "system_install/frontend/app/js/navbar.js":
            result = patch_navbar(content, mark)
        elif relative in ("system_install/frontend/app/js/engine.js", "system_install/frontend/app/js/progress.js"):
            # Preserve the license comment and every executable instruction;
            # replace only the named user-facing literals and image references.
            result = content.replace("'pearOS NiceC0re will be installed on the disk", "'Xodus will be installed on the disk")
            result = result.replace("'You need an active internet connection to install pearOS NiceCC0re", "'You need an active internet connection to install Xodus")
            result = result.replace("your new pearintosh,", "your new Xodus system,")
            result = references(result)
            if relative.endswith("/js/engine.js"):
                result = patch_disk_selection(result)
        elif relative == "post-install/app/js/engine.js":
            # Product hostname defaults are identity strings; all validation,
            # file operations and upstream theme compatibility paths stay intact.
            result = content.replace("'pearOS-machine'", "'Xodus-machine'")
        if result != content:
            updates[relative] = result
    require(len(updates) >= 45, "unexpectedly small frontend identity patch")
    # This point is the first mutation. Names, disk values, onclick handlers,
    # IPC channels and backend commands stay in their existing source files.
    for relative, content in updates.items():
        write(root / relative, content)
    for app in APP_ROOTS:
        shutil.copyfile(HERE / "xodus-installer.css", root / app / "css/xodus-installer.css")
        for name in assets:
            if name.startswith("assets/"):
                target = root / app / "resources" / Path(name).name
                shutil.copyfile(HERE / name, target)
    # Keep the original license presentation and authorship independently of
    # the Xodus interface, including original URLs and component names.
    notices = root / "xodus-upstream-notices"
    notices.mkdir(exist_ok=False)
    for relative, content in original.items():
        if relative.endswith(".html") and b'class="license' in content:
            (notices / relative.replace("/", "__")).write_bytes(content)
    (notices / "progress.js.txt").write_bytes(original["system_install/frontend/app/js/progress.js"])
    # Attribution is kept as source bytes, independently of the visible name.
    for relative, expected in protected_before.items():
        require(digest(root / relative) == expected, f"protected install behavior changed: {relative}")
    record = {"schema": 1, "installer_commit": manifest["installer_commit"],
              "setup_blob": blob, "modified_frontend": {name: digest(root / name) for name in updates},
              "protected": protected_before, "identity_assets": assets}
    write(root / "xodus-frontend-identity.json", json.dumps(record, indent=2) + "\n")
    print(f"Applied Xodus graphical installer identity to {len(updates)} frontend files; protected backend hashes unchanged")
    return sorted(updates)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer_root", type=Path)
    args = parser.parse_args()
    try:
        transform(args.installer_root)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

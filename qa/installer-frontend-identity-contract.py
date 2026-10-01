#!/usr/bin/env python3
"""Verify presentation derivation against real locked installer/package sources."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

REPO = Path(__file__).resolve().parents[1]
IDENTITY = REPO / "overlay/identity/installer"
PIN = "e676698b4a07f797a50fd25241a738ead75248e6"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, IDENTITY / f"apply-{name}-identity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def archive(source: Path, target: Path):
    data = subprocess.check_output(["git", "-C", str(source), "archive", PIN])
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data)) as package:
        for entry in package:
            path = target / entry.name
            assert target.resolve() in path.resolve().parents, entry.name
            assert entry.isdir() or entry.isfile(), entry.name
            if entry.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(package.extractfile(entry).read())


def run(source: Path, calamares: Path | None):
    installer = load("installer")
    manifest = json.loads((IDENTITY / "source-checksums.json").read_text())
    with tempfile.TemporaryDirectory(prefix="xodus-installer-identity-") as temp:
        root = Path(temp) / "installer"
        archive(source, root)
        before = snapshot(root)
        installer.transform(root)
        after = snapshot(root)
        for name in manifest["protected"]:
            assert before[name] == after[name], f"protected backend changed: {name}"
        # Renderer controllers retain their behavior except the reviewed fix
        # that disables Continue until the actual disk page has a selection.
        for name in ("system_install/frontend/app/js/engine.js", "system_install/frontend/app/js/progress.js"):
            expected = before[name].replace(b"\r\n", b"\n").decode("utf-8-sig")
            expected = expected.replace("'pearOS NiceC0re will be installed on the disk", "'Xodus will be installed on the disk")
            expected = expected.replace("'You need an active internet connection to install pearOS NiceCC0re", "'You need an active internet connection to install Xodus")
            expected = expected.replace("your new pearintosh,", "your new Xodus system,")
            for old, new in installer.ICONS.items():
                expected = expected.replace(old, new)
            if name.endswith("/js/engine.js"):
                expected = expected.replace("allButtons[j].getAttribute('onclick').includes('select_disk')",
                    "(allButtons[j].getAttribute('onclick').includes('select_disk') || allButtons[j].getAttribute('onclick').includes('showEraseModal'))")
                expected = expected.replace("if (!hasSelection || (selectedDisk && (selectedDisk.value === '/dev/null'",
                    "if (!hasSelection || !selectedDisk || !selectedDisk.value || (selectedDisk && (selectedDisk.value === '/dev/null'")
            assert after[name].decode() == expected, f"renderer behavior changed: {name}"
        name = "post-install/app/js/engine.js"
        assert after[name].decode() == before[name].replace(b"\r\n", b"\n").decode().replace("'pearOS-machine'", "'Xodus-machine'")
        for name in manifest["frontend"]:
            if name.endswith(".html"):
                pattern = rb'<p\b[^>]*class="license(?:-agreement)?"[^>]*>.*?</p>'
                assert re.findall(pattern, before[name].replace(b"\r\n", b"\n"), re.S) == re.findall(pattern, after[name], re.S), name
                # Control identifiers and navigation/confirmation callbacks
                # remain the same after normalizing the product label.
                pattern = rb'\b(?:id|name|onclick|onload|data-nav)="([^"]*)"'
                original_controls = [installer.visible_text(x.decode()) for x in re.findall(pattern, before[name])]
                assert original_controls == [x.decode() for x in re.findall(pattern, after[name])], name
            elif name.startswith("post-install/app/i18n/"):
                expected = installer.visible_text(before[name].replace(b"\r\n", b"\n").decode("utf-8-sig"))
                assert json.loads(after[name]) == json.loads(expected), name
        assert b"pearintosh" not in after["system_install/frontend/app/js/progress.js"][1500:]
        assert b"https://pearos.xyz/legal/license" not in after["system_install/frontend/app/lg/cs/page_install_agreement.html"]
        assert b'"pear OS' not in after["post-install/app/i18n/ro_RO.json"]
        for group, relative in (("backend", "system_install/setup"), ("frontend", "system_install/frontend/app/js/engine.js")):
            drift = Path(temp) / f"drift-{group}"
            archive(source, drift)
            file = drift / relative
            file.write_bytes(file.read_bytes() + b"\n# drift\n")
            original = snapshot(drift)
            try:
                installer.transform(drift)
                raise AssertionError(f"accepted changed {group}")
            except ValueError as error:
                assert "checksum changed" in str(error)
            assert snapshot(drift) == original, "source drift changed files before rejection"
        if calamares:
            live = Path(temp) / "live"
            shutil.copytree(calamares, live / "etc/calamares")
            before_package = snapshot(live)
            apply_calamares = load("calamares")
            apply_calamares.transform(live)
            after_package = snapshot(live)
            for name, data in before_package.items():
                if name == "etc/calamares/settings.conf":
                    assert after_package[name] == data.replace(b"branding: pearOS", b"branding: Xodus")
                else:
                    assert after_package[name] == data, f"Calamares source changed: {name}"
            broken = Path(temp) / "live-drift"
            shutil.copytree(calamares, broken / "etc/calamares")
            file = broken / "etc/calamares/settings.conf"
            file.write_bytes(file.read_bytes() + b"\n# drift\n")
            baseline = snapshot(broken)
            try:
                apply_calamares.transform(broken)
                raise AssertionError("accepted Calamares package drift")
            except ValueError as error:
                assert "package source changed" in str(error)
            assert snapshot(broken) == baseline
    print("Installer frontend identity contract: PASS (backend, legal bodies, safety controls and source drift)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer_source", type=Path, help="Git checkout containing the locked commit")
    parser.add_argument("--calamares-root", type=Path, help="Audited package's etc/calamares directory")
    args = parser.parse_args()
    run(args.installer_source.resolve(), args.calamares_root.resolve() if args.calamares_root else None)

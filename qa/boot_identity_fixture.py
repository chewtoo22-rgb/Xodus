#!/usr/bin/env python3
"""Add the locked upstream boot text to a disposable overlay test fixture.

The JSON contains text from the ISO commit in upstream/iso.lock. Dummy bytes
stand in for artwork that the overlay replaces; they are never release assets.
"""
import json
from pathlib import Path, PurePosixPath
import sys


def make_fixture(root: Path) -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures/boot-source.json").read_text())
    lock = (Path(__file__).resolve().parents[1] / "upstream/iso.lock").read_text()
    if fixture["upstream_commit"] not in lock:
        raise ValueError("boot fixture no longer matches the pinned ISO source")
    files = dict(fixture["files"])
    for relative in (
        "pear/efiboot/ploader/theme/bg/background.png",
        "pear/efiboot/ploader/theme/icons/os_pearos.png",
        "pear/syslinux/splash.png",
        "pear/airootfs/usr/share/grub/themes/pearOS/background.png",
    ):
        files[relative] = "DISPOSABLE TEST ASSET\n"
    root = root.resolve()
    if root == Path(root.anchor):
        raise ValueError("expected disposable fixture root")
    builder = root / 'build-binary'
    if builder.is_file():
        text = builder.read_text()
        paths = ('usr/share/plasma/look-and-feel/org.kde.breezedark.desktop', 'usr/share/icons/breeze-dark')
        if all(path not in text for path in paths):
            text += '\n_xodus_fixture_dependency_cleanup() {\n    :\n' + ''.join(
                '    rm -rf "${pacstrap_dir}/' + path + '"\n' for path in paths) + '}\n'
            builder.write_text(text, newline='\n')
    for relative in files:
        if ".." in PurePosixPath(relative).parts or not relative.startswith("pear/"):
            raise ValueError("unsafe fixture path")
        target = root / relative
        if target.exists() or target.is_symlink() or root not in target.resolve().parents:
            raise ValueError(f"fixture target exists or escapes root: {relative}")
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: boot_identity_fixture.py <disposable-source-root>")
    make_fixture(Path(sys.argv[1]))

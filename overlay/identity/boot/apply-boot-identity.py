#!/usr/bin/env python3
"""Apply the Xodus boot identity to one checkout of the pinned ISO source.

Every expected upstream text/asset shape is checked before any file changes.
The caller uses a fresh pinned checkout for each build.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
import shutil
import struct
import sys


BOOT = Path(__file__).resolve().parent
ASSETS = BOOT / "assets"
MASTER = BOOT / "source/xodus-boot-master.mp4"
MASTER_SHA256 = "1d114cddaba483c554d375a978b6474e57d20d70f88836903494c111c8ceb90b"
FRAME_COUNT = 241
REQUIRED_PNGS = {
    "ploader-background.png": (1920, 1080),
    "grub-background.png": (1920, 1080),
    "syslinux-splash.png": (640, 480),
    "os_xodus.png": (128, 128),
    **{f"plymouth/frame-{index:03d}.png": (960, 540) for index in range(FRAME_COUNT)},
}


def die(message: str) -> None:
    raise SystemExit(f"Xodus boot identity: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_file(root: Path, relative: str) -> Path:
    path = root / relative
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        die(f"expected regular pinned-source file is missing or unsafe: {relative}")
    return path


def write_lf(path: Path, content: str) -> None:
    # This helper is also exercised from Windows; source shell files must stay
    # LF-only for the Arch builder and installed target scripts.
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def exact(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if text.count(old) != count or new in text:
        die(f"pinned source layout changed: {label}")
    return text.replace(old, new)


def check_png(path: Path, width: int, height: int) -> None:
    if not path.is_file() or path.is_symlink():
        die(f"derived PNG is missing or unsafe: {path.relative_to(BOOT)}")
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        die(f"invalid PNG: {path.relative_to(BOOT)}")
    if struct.unpack(">II", data[16:24]) != (width, height):
        die(f"unexpected PNG dimensions: {path.relative_to(BOOT)}")


def verify_assets() -> None:
    if not MASTER.is_file() or MASTER.is_symlink() or sha256(MASTER) != MASTER_SHA256:
        die("approved video master is missing or changed")
    manifest = BOOT / "source/assets.sha256"
    if not manifest.is_file() or manifest.is_symlink():
        die("derived asset checksum manifest is missing")
    hashes = {}
    for line in manifest.read_text(encoding="ascii").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2 or parts[1] in hashes or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            die("derived asset checksum manifest is malformed")
        hashes[parts[1]] = parts[0]
    if set(hashes) != set(REQUIRED_PNGS):
        die("derived asset checksum inventory changed")
    if {path.relative_to(ASSETS).as_posix() for path in ASSETS.rglob("*.png")} != set(REQUIRED_PNGS):
        die("derived PNG inventory contains missing or unreviewed files")
    for relative, (width, height) in REQUIRED_PNGS.items():
        path = ASSETS / relative
        check_png(path, width, height)
        if sha256(path) != hashes[relative]:
            die(f"derived asset hash changed: {relative}")
    for relative in ("xodus.plymouth", "xodus.script", "grub-theme.txt"):
        path = BOOT / relative
        if not path.is_file() or path.is_symlink():
            die(f"Plymouth theme file is missing: {relative}")


def transform(root: Path) -> None:
    pear = root / "pear"
    if root == Path("/") or not pear.is_dir() or pear.is_symlink():
        die("expected pinned ISO source root")
    verify_assets()

    files = {
        "ploader": "pear/efiboot/ploader/ploader.conf",
        "ploader_linux": "pear/efiboot/ploader/ploader_linux.conf",
        "syslinux_head": "pear/syslinux/archiso_head.cfg",
        "syslinux_live": "pear/syslinux/archiso_sys-linux.cfg",
        "syslinux_pxe": "pear/syslinux/archiso_pxe-linux.cfg",
        "customize": "pear/airootfs/root/customize_airootfs.sh",
        "grub_defaults": "pear/airootfs/etc/default/grub",
        "finalisation": "pear/airootfs/usr/local/bin/alg-finalisation",
        "grub_theme": "pear/airootfs/usr/share/grub/themes/pearOS/theme.txt",
        "initramfs_hooks": "pear/airootfs/etc/mkinitcpio.conf",
        "loader_normal": "pear/efiboot/loader/entries/01-archiso-x86_64-linux.conf",
        "loader_debug": "pear/efiboot/loader/entries/02-archiso-x86_64-linux-no-plymouth.conf",
        "loader_legacy": "pear/efiboot/loader/entries/03-archiso-x86_64-linux-legacy.conf",
    }
    source = {key: checked_file(root, relative) for key, relative in files.items()}
    for relative in (
        "pear/efiboot/ploader/theme/bg/background.png",
        "pear/efiboot/ploader/theme/icons/os_pearos.png",
        "pear/syslinux/splash.png",
        "pear/airootfs/usr/share/grub/themes/pearOS/background.png",
    ):
        checked_file(root, relative)
    theme_dir = root / "pear/airootfs/usr/share/grub/themes/pearOS"
    if any(path.is_symlink() for path in theme_dir.rglob("*")):
        die("upstream GRUB theme contains an unreviewed symlink")
    if (theme_dir.parent / "Xodus").exists():
        die("Xodus GRUB theme already exists in the pinned source")
    plymouth_dir = root / "pear/airootfs/usr/share/plymouth/themes/xodus"
    if plymouth_dir.exists():
        die("Xodus Plymouth theme already exists in the pinned source")

    old = {key: path.read_text(encoding="utf-8") for key, path in source.items()}
    new = {}
    new["ploader"] = exact(old["ploader"], 'default_selection "pearOS NiceC0re"',
                           'default_selection "Xodus"', "Ploader default")
    new["ploader"] = exact(new["ploader"], 'icon    /EFI/BOOT/theme/icons/os_pearos.png',
                           'icon    /EFI/BOOT/theme/icons/os_xodus.png', "Ploader icon")
    if new["ploader"].count("pearOS NiceC0re") != 3:
        die("Ploader menu entry count changed")
    new["ploader"] = new["ploader"].replace("pearOS NiceC0re", "Xodus")
    new["ploader_linux"] = exact(old["ploader_linux"], "pearOS NiceC0re", "Xodus", "Ploader fallback")
    for key in ("loader_normal", "loader_debug", "loader_legacy"):
        new[key] = exact(old[key], "pearOS NiceC0re", "Xodus", f"Ventoy/systemd boot title: {key}")
    new["syslinux_head"] = exact(old["syslinux_head"], "MENU TITLE pearOS NiceC0re",
                                "MENU TITLE Xodus live environment", "BIOS menu title")
    new["syslinux_head"] = exact(new["syslinux_head"],
                                  'MENU COLOR unsel        37;44   #50ffffff #a0000000 std',
                                  'MENU COLOR unsel        37;44   #e0eee8ff #a0000000 std',
                                  "BIOS menu text contrast")
    for key in ("syslinux_live", "syslinux_pxe"):
        if "pearOS" not in old[key]:
            die(f"pinned source layout changed: {key}")
        new[key] = old[key].replace("pearOS NiceC0re", "Xodus").replace("pearOS", "Xodus")
        if "pearOS" in new[key]:
            die(f"unreplaced BIOS label: {key}")

    new["customize"] = exact(old["customize"], 'echo "pearOS" > /etc/arch-release',
                             'echo "Xodus" > /etc/arch-release', "/etc/arch-release")
    plymouth_old = '''if command -v plymouth-set-default-theme &> /dev/null; then
\techo "Setting plymouth theme"
\tplymouth-set-default-theme -R pear-plymouth && \\
\t\techo "Success!" || \\
\t\techo "Failed to set plymouth theme"
else
\techo "Plymouth command theme not found"
fi'''
    plymouth_new = '''command -v plymouth-set-default-theme >/dev/null 2>&1 || {
    echo "Plymouth is required for the Xodus boot theme" >&2
    exit 1
}
plymouth-set-default-theme -R xodus
[[ "$(plymouth-set-default-theme)" == xodus ]] || {
    echo "Xodus Plymouth theme was not selected" >&2
    exit 1
}'''
    new["customize"] = exact(new["customize"], plymouth_old, plymouth_new,
                             "pre-initramfs Plymouth selection")
    new["grub_defaults"] = exact(old["grub_defaults"], 'GRUB_DISTRIBUTOR="Arch"',
                                 'GRUB_DISTRIBUTOR="Xodus"', "GRUB distributor")
    new["grub_defaults"] = exact(new["grub_defaults"],
                                 'GRUB_THEME="/usr/share/grub/themes/pearOS/theme.txt"',
                                 'GRUB_THEME="/usr/share/grub/themes/Xodus/theme.txt"',
                                 "installed GRUB theme path")
    new["grub_defaults"] = exact(new["grub_defaults"],
                                 'GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 quiet audit=0"',
                                 'GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 quiet splash audit=0"',
                                 "installed splash command line")
    new["finalisation"] = exact(old["finalisation"],
                                'GRUB_DISTRIBUTOR="pearOS NiceC0re"',
                                'GRUB_DISTRIBUTOR="Xodus"',
                                "installed GRUB finalisation")
    # Validate the upstream title before replacing its pale-panel theme with
    # our own dark, transparent menu. Keep the upstream fonts and notices.
    exact(old["grub_theme"], 'text="pearOS Bootloader"', 'text="Xodus"', "GRUB theme title")
    new["grub_theme"] = (BOOT / "grub-theme.txt").read_text(encoding="utf-8")
    hooks = [line for line in old["initramfs_hooks"].splitlines() if line.startswith("HOOKS=")]
    if len(hooks) != 1 or " plymouth " not in hooks[0]:
        die("pinned live initramfs no longer includes Plymouth")

    # All validation above is read-only. Apply only after the full contract
    # and approved asset inventory are known to match.
    for key, content in new.items():
        if key == "grub_theme":
            continue
        write_lf(source[key], content)
    shutil.copy2(ASSETS / "ploader-background.png",
                 root / "pear/efiboot/ploader/theme/bg/background.png")
    shutil.copy2(ASSETS / "os_xodus.png",
                 root / "pear/efiboot/ploader/theme/icons/os_xodus.png")
    shutil.copy2(ASSETS / "syslinux-splash.png", root / "pear/syslinux/splash.png")
    shutil.copytree(theme_dir, theme_dir.parent / "Xodus")
    write_lf(theme_dir.parent / "Xodus/theme.txt", new["grub_theme"])
    shutil.copy2(ASSETS / "grub-background.png", theme_dir.parent / "Xodus/background.png")
    plymouth_dir.mkdir(parents=True)
    shutil.copy2(BOOT / "xodus.plymouth", plymouth_dir / "xodus.plymouth")
    shutil.copy2(BOOT / "xodus.script", plymouth_dir / "xodus.script")
    for index in range(FRAME_COUNT):
        name = f"frame-{index:03d}.png"
        shutil.copy2(ASSETS / "plymouth" / name, plymouth_dir / name)

    if 'pearOS' in source["ploader"].read_text(encoding="utf-8"):
        die("Ploader still exposes pearOS")
    if not (plymouth_dir / "frame-240.png").is_file():
        die("staged Plymouth animation is incomplete")
    if 'GRUB_THEME="/usr/share/grub/themes/Xodus/theme.txt"' not in source["grub_defaults"].read_text():
        die("installed GRUB theme path was not updated")
    print("Applied Xodus Ploader, BIOS, Plymouth and installed GRUB boot identity")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        die("usage: apply-boot-identity.py <pinned-iso-source-root>")
    transform(Path(sys.argv[1]).resolve(strict=True))

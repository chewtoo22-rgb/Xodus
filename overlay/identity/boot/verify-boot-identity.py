#!/usr/bin/env python3
"""Verify boot identity in a source tree or extracted/staged build payload.

Use --live-root for pacstrap or extracted squashfs, --efi-root for extracted
EFI FAT, --iso-root for the ISO 9660 tree, and --initramfs-root after unpacking
the live initramfs. Checks inspect retained bytes, never source-only claims.
"""
from __future__ import annotations

import argparse
import configparser
import hashlib
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
FRAME_COUNT = 241


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def regular(root: Path, relative: str) -> Path:
    path = root / relative
    require(path.is_file() and not path.is_symlink() and root in path.resolve().parents,
            f"missing or unsafe retained file: {relative}")
    return path


def text(root: Path, relative: str) -> str:
    return regular(root, relative).read_text(encoding="utf-8")


def asset_hashes() -> dict[str, str]:
    result = {}
    for line in (HERE / "source/assets.sha256").read_text(encoding="ascii").splitlines():
        digest, relative = line.split("  ", 1)
        require(bool(re.fullmatch(r"[0-9a-f]{64}", digest)) and relative not in result,
                "invalid reference asset checksum manifest")
        result[relative] = digest
    expected = {"ploader-background.png", "grub-background.png", "syslinux-splash.png", "os_xodus.png"}
    expected.update(f"plymouth/frame-{index:03d}.png" for index in range(FRAME_COUNT))
    require(set(result) == expected, "reference boot asset inventory changed")
    return result


def match_asset(root: Path, relative: str, reference: str, hashes: dict[str, str]) -> None:
    actual = hashlib.sha256(regular(root, relative).read_bytes()).hexdigest()
    require(actual == hashes[reference], f"retained boot asset differs from approved export: {relative}")


def theme(root: Path, hashes: dict[str, str]) -> None:
    base = "usr/share/plymouth/themes/xodus"
    for name in ("xodus.plymouth", "xodus.script"):
        require(regular(root, f"{base}/{name}").read_bytes() == (HERE / name).read_bytes(),
                f"retained Plymouth theme differs from reviewed source: {name}")
    frames = {p.name for p in (root / base).glob("frame-*.png")}
    require(frames == {f"frame-{index:03d}.png" for index in range(FRAME_COUNT)},
            "retained Plymouth film has missing or unreviewed frames")
    for index in range(FRAME_COUNT):
        match_asset(root, f"{base}/frame-{index:03d}.png", f"plymouth/frame-{index:03d}.png", hashes)


def selected_theme(root: Path) -> None:
    conf = "etc/plymouth/plymouthd.conf"
    parser = configparser.ConfigParser(strict=True)
    parser.read_string(text(root, conf))
    require(parser.get("Daemon", "Theme", fallback="") == "xodus",
            "retained Plymouth default theme is not xodus")


def grub(root: Path, hashes: dict[str, str]) -> None:
    defaults = text(root, "etc/default/grub")
    require('GRUB_DISTRIBUTOR="Xodus"' in defaults and
            'GRUB_THEME="/usr/share/grub/themes/Xodus/theme.txt"' in defaults,
            "installed GRUB identity/default theme changed")
    cmdline = re.findall(r'^GRUB_CMDLINE_LINUX_DEFAULT="([^"]*)"$', defaults, re.M)
    require(len(cmdline) == 1 and "splash" in cmdline[0].split(),
            "installed GRUB command line will not show the boot sequence")
    require(regular(root, "usr/share/grub/themes/Xodus/theme.txt").read_bytes() ==
            (HERE / "grub-theme.txt").read_bytes(), "installed GRUB theme differs from reviewed source")
    match_asset(root, "usr/share/grub/themes/Xodus/background.png", "grub-background.png", hashes)


def firmware(root: Path, prefix: str, hashes: dict[str, str]) -> None:
    conf = text(root, f"{prefix}/ploader.conf")
    require("pearOS" not in conf and 'default_selection "Xodus"' in conf and
            conf.count('menuentry "Xodus') == 3 and "os_xodus.png" in conf,
            "firmware boot menu still exposes upstream identity or lost a boot mode")
    require("quiet splash" in conf and "No Plymouth (Debug)" in conf and "nomodeset" in conf,
            "firmware normal/debug/legacy boot choices changed")
    match_asset(root, f"{prefix}/theme/bg/background.png", "ploader-background.png", hashes)
    match_asset(root, f"{prefix}/theme/icons/os_xodus.png", "os_xodus.png", hashes)


def source_root(root: Path, hashes: dict[str, str]) -> None:
    firmware(root, "pear/efiboot/ploader", hashes)
    loader_entries(root, "pear/efiboot/loader/entries")
    for name in ("archiso_head.cfg", "archiso_sys-linux.cfg", "archiso_pxe-linux.cfg"):
        config = text(root, f"pear/syslinux/{name}")
        require("pearOS" not in config and "Xodus" in config, f"BIOS boot identity changed: {name}")
    match_asset(root, "pear/syslinux/splash.png", "syslinux-splash.png", hashes)
    live = root / "pear/airootfs"
    theme(live, hashes)
    grub(live, hashes)
    customize = text(live, "root/customize_airootfs.sh")
    require("plymouth-set-default-theme -R xodus" in customize and "-R pear-plymouth" not in customize,
            "Xodus theme is not selected before live initramfs regeneration")
    hooks = re.findall(r'^HOOKS=\(([^)]*)\)', text(live, "etc/mkinitcpio.conf"), re.M)
    require(len(hooks) == 1 and "plymouth" in hooks[0].split(), "live initramfs lost Plymouth hook")
    require('GRUB_DISTRIBUTOR="Xodus"' in text(live, "usr/local/bin/alg-finalisation"),
            "installed finalisation would restore upstream GRUB identity")


def loader_entries(root: Path, prefix: str) -> None:
    for name in ("01-archiso-x86_64-linux.conf", "02-archiso-x86_64-linux-no-plymouth.conf",
                 "03-archiso-x86_64-linux-legacy.conf"):
        config = text(root, f"{prefix}/{name}")
        require("pearOS" not in config and re.search(r"^title\s+Xodus", config, re.M),
                f"Ventoy/systemd-boot title changed: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for kind in ("source", "live", "efi", "iso", "initramfs"):
        parser.add_argument(f"--{kind}-root", type=Path)
    args = parser.parse_args()
    require(any(vars(args).values()), "provide at least one retained payload root")
    hashes = asset_hashes()
    for key, value in vars(args).items():
        if value is None:
            continue
        root = value.resolve(strict=True)
        if key == "source_root":
            source_root(root, hashes)
        elif key == "live_root":
            theme(root, hashes)
            selected_theme(root)
            grub(root, hashes)
            require(text(root, "etc/arch-release").strip() == "Xodus", "live arch-release identity changed")
        elif key == "initramfs_root":
            theme(root, hashes)
            selected_theme(root)
        elif key == "efi_root":
            firmware(root, "EFI/BOOT", hashes)
        elif key == "iso_root":
            firmware(root, "EFI/BOOT", hashes)
            loader_entries(root, "loader/entries")
            config = text(root, "syslinux/archiso_head.cfg")
            require("pearOS" not in config and "MENU TITLE Xodus live environment" in config,
                    "retained BIOS boot menu title changed")
            match_asset(root, "syslinux/splash.png", "syslinux-splash.png", hashes)
        print(f"Xodus boot identity: {key}=pass")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, configparser.Error) as exc:
        raise SystemExit(f"Xodus boot identity: {exc}") from exc

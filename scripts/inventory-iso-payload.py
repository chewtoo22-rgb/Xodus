#!/usr/bin/env python3
"""Inventory the retained root and boot payload of one pinned Core ISO build.

The inventory records what the build staged. It is evidence for a subsequent
redistribution review, not a license decision or a substitute for ISO signing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
PACKAGE_RE = re.compile(r"[A-Za-z0-9@._+\-]+\Z")
VERSION_RE = re.compile(r"\S+\Z")
LICENSE_NAMES = ("license", "licence", "copying", "notice", "copyright")
WALLPAPER_PARTS = {"wallpaper", "wallpapers", "background", "backgrounds"}


class InventoryError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head(repo: Path) -> str:
    try:
        value = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InventoryError(f"cannot read Git HEAD in {repo}") from exc
    require(bool(SHA_RE.fullmatch(value)), f"invalid Git HEAD in {repo}")
    return value


def noncomment_lines(path: Path) -> list[str]:
    require(path.is_file(), f"missing lock file: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def locked_commits(xodus_root: Path) -> tuple[str, str]:
    iso_lines = noncomment_lines(xodus_root / "upstream/iso.lock")
    require(len(iso_lines) == 1, "ISO lock must contain exactly one source")
    iso_fields = iso_lines[0].split("|")
    require(len(iso_fields) == 4 and bool(SHA_RE.fullmatch(iso_fields[2])),
            "ISO lock has an invalid commit")

    installer_lines = noncomment_lines(xodus_root / "upstream/installer.lock")
    refs = [line.removeprefix("REF=") for line in installer_lines if line.startswith("REF=")]
    require(len(refs) == 1 and bool(SHA_RE.fullmatch(refs[0])),
            "installer lock must contain one valid REF")
    return iso_fields[2], refs[0]


def unique_path(paths: list[Path], description: str) -> Path:
    require(len(paths) == 1, f"expected exactly one {description}; found {len(paths)}")
    return paths[0]


def desc_sections(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("%") and line.endswith("%") and len(line) > 2:
            current = line[1:-1]
            require(current not in sections, f"duplicate %{current}% in {path}")
            sections[current] = []
        elif line and current is not None:
            sections[current].append(line)
    return sections


def installed_packages(root: Path) -> dict[str, tuple[str, tuple[str, ...]]]:
    db = root / "var/lib/pacman/local"
    require(db.is_dir(), f"missing installed pacman database: {db}")
    descs = sorted(db.glob("*/desc"))
    require(bool(descs), "installed pacman database contains no desc records")
    packages: dict[str, tuple[str, tuple[str, ...]]] = {}
    for desc in descs:
        fields = desc_sections(desc)
        names = fields.get("NAME", [])
        versions = fields.get("VERSION", [])
        require(len(names) == 1 and bool(PACKAGE_RE.fullmatch(names[0])),
                f"invalid package name in {desc}")
        require(len(versions) == 1 and bool(VERSION_RE.fullmatch(versions[0])),
                f"invalid package version in {desc}")
        name, version = names[0], versions[0]
        require(name not in packages, f"duplicate installed package: {name}")
        licenses = tuple(fields.get("LICENSE", []))
        require(all("\t" not in item for item in licenses),
                f"invalid license entry for {name}")
        packages[name] = (version, licenses)
    return packages


def verify_pkglist(path: Path, packages: dict[str, tuple[str, tuple[str, ...]]]) -> None:
    require(path.is_file(), f"missing staged package list: {path}")
    listed: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        require(len(parts) == 2, f"malformed package list line: {line!r}")
        name, version = parts
        require(name not in listed, f"duplicate package list entry: {name}")
        listed[name] = version
    from_db = {name: record[0] for name, record in packages.items()}
    require(listed == from_db, "staged pkglist differs from installed pacman desc records")


def verify_welcome_payload(xodus_root: Path, stage: Path) -> None:
    """Gate the M1 Welcome files only when this source checkout ships them."""
    source = xodus_root / "overlay/identity/welcome/xodus-welcome.cpp"
    if not source.exists() and not source.is_symlink():
        return
    require(source.is_file() and not source.is_symlink(),
            "Xodus Welcome source is not a regular file")

    binary = stage / "usr/lib/xodus/xodus-welcome"
    require(binary.is_file() and not binary.is_symlink(),
            "staged Xodus Welcome executable is missing or unsafe")
    with binary.open("rb") as stream:
        require(stream.read(4) == b"\x7fELF",
                "staged Xodus Welcome is not an ELF executable")
    require(stat.S_IMODE(binary.stat().st_mode) == 0o755,
            "staged Xodus Welcome must have mode 0755")

    for relative in ("usr/share/applications/welcome.desktop",
                     "etc/skel/.config/autostart/welcome.desktop",
                     "home/liveuser/.config/autostart/welcome.desktop"):
        path = stage / relative
        require(path.is_file() and not path.is_symlink() and
                path.read_text(encoding="utf-8").splitlines() ==
                ["[Desktop Entry]", "Hidden=true"],
                f"upstream Welcome entry is not masked: {relative}")

    for relative in ("usr/share/applications/xodus-welcome.desktop",
                     "etc/skel/.config/autostart/xodus-welcome.desktop",
                     "home/liveuser/.config/autostart/xodus-welcome.desktop"):
        path = stage / relative
        require(path.is_file() and not path.is_symlink(),
                f"Xodus Welcome launcher is missing or unsafe: {relative}")
        lines = path.read_text(encoding="utf-8").splitlines()
        require(lines.count("Name=Xodus Welcome") == 1 and
                lines.count("Exec=/usr/lib/xodus/xodus-welcome") == 1 and
                not any("pearos" in line.lower() for line in lines),
                f"Xodus Welcome launcher has wrong identity: {relative}")
        if relative != "usr/share/applications/xodus-welcome.desktop":
            require(lines.count("OnlyShowIn=KDE;") == 1,
                    f"Xodus Welcome autostart is not KDE-scoped: {relative}")


def verify_graphical_payload(xodus_root: Path, stage: Path,
                             upstream_dir: Path) -> tuple[dict, bytes, str]:
    """Bind actual retained bytes to the produced squashfs verification."""
    checker = xodus_root / "qa/verify-graphical-identity.py"
    require(checker.is_file() and not checker.is_symlink(),
            "retained graphical payload checker is missing or unsafe")
    with tempfile.TemporaryDirectory(prefix="xodus-graphical-inventory-") as temporary:
        report = Path(temporary) / "report.json"
        try:
            result = subprocess.run(
                [sys.executable, str(checker), str(stage), "--repo-root", str(xodus_root),
                 "--output", str(report)], capture_output=True, text=True, timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InventoryError("cannot run retained graphical payload checker") from exc
        require(result.returncode == 0,
                "retained graphical payload failed: " + (result.stderr or result.stdout).strip())
        require(report.is_file() and not report.is_symlink(),
                "retained graphical payload checker did not write its report")
        report_bytes = report.read_bytes()
    produced = upstream_dir / "xodus-graphical-payload-verification.json"
    require(produced.is_file() and not produced.is_symlink(),
            "produced ISO graphical verification report is missing or unsafe")
    try:
        document = json.loads(report_bytes)
        produced_document = json.loads(produced.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InventoryError("invalid graphical payload verification report") from exc
    require(isinstance(document, dict) and document.get("schema_version") == 1 and
            document.get("graphical_identity") == "pass" and
            isinstance(document.get("files"), dict) and bool(document["files"]),
            "graphical payload report has an invalid schema or status")
    require(all(isinstance(name, str) and isinstance(digest, str) and
                bool(re.fullmatch(r"[0-9a-f]{64}", digest))
                for name, digest in document["files"].items()),
            "graphical payload report contains invalid file hashes")
    require(document == produced_document,
            "retained graphical payload differs from produced ISO squashfs")
    return document, report_bytes, sha256_file(produced)


def asset_categories(relative: Path) -> tuple[str, ...]:
    parts = tuple(part.lower() for part in relative.parts)
    name = parts[-1]
    categories = []
    if parts[:3] == ("usr", "share", "licenses") or name.startswith(LICENSE_NAMES):
        categories.append("license_text")
    if any(part in WALLPAPER_PARTS for part in parts[:-1]):
        categories.append("wallpaper")
    return tuple(categories)


def asset_rows(root: Path) -> list[tuple[str, str, str, str, int, str]]:
    rows: list[tuple[str, str, str, str, int, str]] = []
    for directory, subdirs, files in os.walk(root, followlinks=False):
        folder = Path(directory)
        # os.walk does not descend into directory links. Record them so the
        # inventory cannot silently treat a link as an empty wallpaper tree.
        linked_dirs = [name for name in subdirs if (folder / name).is_symlink()]
        subdirs[:] = [name for name in subdirs if name not in linked_dirs]
        for name in sorted(files + linked_dirs):
            path = folder / name
            relative = path.relative_to(root)
            categories = asset_categories(relative)
            if not categories:
                continue
            if path.is_symlink():
                target = os.readlink(path)
                digest = hashlib.sha256(target.encode("utf-8", "surrogateescape")).hexdigest()
                kind, size = "symlink_target", len(target.encode("utf-8", "surrogateescape"))
            elif path.is_file():
                digest = sha256_file(path)
                kind, size, target = "file", path.stat().st_size, ""
            else:
                continue
            for category in categories:
                rows.append((category, relative.as_posix(), kind, digest, size, target))
    return sorted(rows)


def write_tsv(path: Path, header: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def build_inventory(xodus_root: Path, upstream_dir: Path, output_dir: Path,
                    expected_source_commit: str | None) -> None:
    xodus_root = xodus_root.resolve(strict=True)
    upstream_dir = upstream_dir.resolve(strict=True)
    source_commit = git_head(xodus_root)
    if expected_source_commit is not None:
        require(source_commit == expected_source_commit,
                "checked-out Xodus HEAD does not match requested source commit")
    upstream_commit, installer_commit = locked_commits(xodus_root)
    require(git_head(upstream_dir) == upstream_commit,
            "checked-out upstream ISO HEAD does not match iso.lock")

    stage = unique_path(sorted((upstream_dir / "work").glob("tmp.*/x86_64/airootfs")),
                        "retained staged live root")
    require(stage.is_dir() and not stage.is_symlink(), "staged live root is invalid")
    work = stage.parent.parent
    pkglist = work / "iso/arch/pkglist.x86_64.txt"
    packages = installed_packages(stage)
    verify_pkglist(pkglist, packages)
    verify_welcome_payload(xodus_root, stage)
    graphical_report, graphical_bytes, produced_graphical_digest = verify_graphical_payload(
        xodus_root, stage, upstream_dir)

    iso = unique_path(sorted(upstream_dir.glob("Xodus-reference-*.iso")), "built ISO")
    require(iso.is_file() and iso.stat().st_size > 0, "built ISO is empty or missing")
    iso_digest = sha256_file(iso)

    source_efi = upstream_dir / "pear/efiboot/ploader/ploader_x64.efi"
    staged_efi = work / "iso/EFI/BOOT/BOOTx64.EFI"
    firmware_efi = upstream_dir / "xodus-ploader-firmware.efi"
    require(source_efi.is_file() and staged_efi.is_file() and firmware_efi.is_file(),
            "Ploader EFI missing from source, ISO tree, or FAT boot image extraction")
    source_efi_digest = sha256_file(source_efi)
    staged_efi_digest = sha256_file(staged_efi)
    firmware_efi_digest = sha256_file(firmware_efi)
    require(source_efi_digest == staged_efi_digest,
            "staged Ploader EFI differs from pinned upstream source")
    require(source_efi_digest == firmware_efi_digest,
            "FAT boot image Ploader EFI differs from pinned upstream source")

    output_dir.mkdir(parents=True, exist_ok=True)
    package_path = output_dir / "xodus-package-license-inventory.tsv"
    asset_path = output_dir / "xodus-asset-hashes.tsv"
    manifest_path = output_dir / "xodus-payload-inventory.json"
    graphical_path = output_dir / "xodus-retained-graphical-payload-verification.json"
    graphical_path.write_bytes(graphical_bytes)
    package_rows = [
        (name, version, "; ".join(licenses) if licenses else "UNDECLARED")
        for name, (version, licenses) in sorted(packages.items())
    ]
    write_tsv(package_path, ("package", "version", "declared_licenses"), package_rows)
    assets = asset_rows(stage)
    assets.extend([
        ("ploader_source", "pear/efiboot/ploader/ploader_x64.efi", "file",
         source_efi_digest, source_efi.stat().st_size, ""),
        ("ploader_staged", "iso/EFI/BOOT/BOOTx64.EFI", "file",
         staged_efi_digest, staged_efi.stat().st_size, ""),
        ("ploader_firmware", "efiboot.img::/EFI/BOOT/BOOTx64.EFI", "file",
         firmware_efi_digest, firmware_efi.stat().st_size, ""),
    ])
    assets.sort()
    write_tsv(asset_path, ("category", "path", "kind", "sha256", "size_bytes", "link_target"),
              assets)

    manifest = {
        "schema": 1,
        "xodus_source_commit": source_commit,
        "upstream_iso_commit": upstream_commit,
        "installer_commit": installer_commit,
        "iso_filename": iso.name,
        "iso_sha256": iso_digest,
        "package_count": len(packages),
        "packages_without_declared_license_count": sum(not licenses for _, licenses in packages.values()),
        "license_text_entry_count": sum(row[0] == "license_text" for row in assets),
        "wallpaper_entry_count": sum(row[0] == "wallpaper" for row in assets),
        "ploader_efi_sha256": source_efi_digest,
        "package_inventory_sha256": sha256_file(package_path),
        "asset_inventory_sha256": sha256_file(asset_path),
        "graphical_identity": graphical_report,
        "graphical_identity_report": graphical_path.name,
        "graphical_identity_report_sha256": sha256_file(graphical_path),
        "produced_iso_graphical_identity_report_sha256": produced_graphical_digest,
        "scope": "retained live root and staged boot tree; not legal clearance",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Inventoried {len(packages)} packages and {len(assets)} asset entries for {iso.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xodus-root", type=Path, required=True)
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-source-commit")
    args = parser.parse_args()
    try:
        build_inventory(args.xodus_root, args.upstream_dir, args.output_dir,
                        args.expected_source_commit)
    except (InventoryError, OSError, UnicodeError) as exc:
        print(f"ISO payload inventory failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

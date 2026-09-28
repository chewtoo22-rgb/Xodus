"""Synthetic contract for the Core ISO payload inventory."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/inventory-iso-payload.py"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], check=True,
                            capture_output=True, text=True)
    return result.stdout.strip()


def commit(root: Path) -> str:
    git(root, "init", "-q")
    git(root, "config", "user.name", "Xodus QA")
    git(root, "config", "user.email", "qa@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return git(root, "rev-parse", "HEAD")


class PayloadInventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="xodus-inventory-")
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.upstream = base / "upstream-src"
        self.xodus = base / "xodus"
        self.output = base / "inventory"
        source_efi = self.upstream / "pear/efiboot/ploader/ploader_x64.efi"
        source_efi.parent.mkdir(parents=True)
        source_efi.write_bytes(b"pinned prebuilt EFI fixture\0")
        upstream_commit = commit(self.upstream)

        locks = self.xodus / "upstream"
        locks.mkdir(parents=True)
        (locks / "iso.lock").write_text(
            "https://example.invalid/iso.git|main|" + upstream_commit + "|2026-09-28T00:00:00Z\n",
            encoding="utf-8",
        )
        installer_commit = "a" * 40
        (locks / "installer.lock").write_text(
            "REPO=https://example.invalid/installer.git\nREF=" + installer_commit + "\n",
            encoding="utf-8",
        )
        self.source_commit = commit(self.xodus)

        self.work = self.upstream / "work/tmp.fixture"
        root = self.work / "x86_64/airootfs"
        desc = root / "var/lib/pacman/local/example-1.2-3/desc"
        desc.parent.mkdir(parents=True)
        desc.write_text("%NAME%\nexample\n\n%VERSION%\n1.2-3\n\n%LICENSE%\nMIT\n\n",
                        encoding="utf-8")
        pkglist = self.work / "iso/arch/pkglist.x86_64.txt"
        pkglist.parent.mkdir(parents=True)
        pkglist.write_text("example 1.2-3\n", encoding="utf-8")
        license_file = root / "usr/share/licenses/example/LICENSE"
        license_file.parent.mkdir(parents=True)
        license_file.write_text("sample license\n", encoding="utf-8")
        wallpaper = root / "usr/share/extras/wallpapers/wall.png"
        wallpaper.parent.mkdir(parents=True)
        wallpaper.write_bytes(b"synthetic wallpaper")
        staged_efi = self.work / "iso/EFI/BOOT/BOOTx64.EFI"
        staged_efi.parent.mkdir(parents=True)
        staged_efi.write_bytes(source_efi.read_bytes())
        (self.upstream / "xodus-ploader-firmware.efi").write_bytes(source_efi.read_bytes())
        (self.upstream / "Xodus-reference-fixture.iso").write_bytes(b"synthetic ISO")

    def run_inventory(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--xodus-root", str(self.xodus),
             "--upstream-dir", str(self.upstream), "--output-dir", str(self.output),
             "--expected-source-commit", self.source_commit],
            text=True, capture_output=True,
        )

    def test_inventory_is_bound_and_deterministic(self) -> None:
        result = self.run_inventory()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest_path = self.output / "xodus-payload-inventory.json"
        package_path = self.output / "xodus-package-license-inventory.tsv"
        asset_path = self.output / "xodus-asset-hashes.tsv"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["xodus_source_commit"], self.source_commit)
        self.assertEqual(manifest["iso_sha256"], hashlib.sha256(b"synthetic ISO").hexdigest())
        self.assertEqual(manifest["package_count"], 1)
        self.assertEqual(manifest["license_text_entry_count"], 1)
        self.assertEqual(manifest["wallpaper_entry_count"], 1)
        with package_path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(rows, [{"package": "example", "version": "1.2-3",
                                 "declared_licenses": "MIT"}])
        with asset_path.open(newline="", encoding="utf-8") as stream:
            assets = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual({row["category"] for row in assets},
                         {"license_text", "wallpaper", "ploader_source", "ploader_staged",
                          "ploader_firmware"})
        first = [path.read_bytes() for path in (manifest_path, package_path, asset_path)]
        self.assertEqual(self.run_inventory().returncode, 0)
        self.assertEqual(first, [path.read_bytes() for path in
                                 (manifest_path, package_path, asset_path)])

    def test_rejects_package_list_drift(self) -> None:
        (self.work / "iso/arch/pkglist.x86_64.txt").write_text("example 2.0-1\n",
                                                               encoding="utf-8")
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pkglist differs", result.stderr)

    def test_rejects_multiple_retained_roots(self) -> None:
        (self.upstream / "work/tmp.second/x86_64/airootfs").mkdir(parents=True)
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one retained staged live root", result.stderr)

    def test_rejects_changed_staged_efi(self) -> None:
        (self.work / "iso/EFI/BOOT/BOOTx64.EFI").write_bytes(b"different EFI")
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from pinned upstream source", result.stderr)

    def test_rejects_changed_firmware_efi(self) -> None:
        (self.upstream / "xodus-ploader-firmware.efi").write_bytes(b"different EFI")
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAT boot image Ploader EFI differs", result.stderr)

    def test_rejects_a_source_commit_other_than_checked_out_head(self) -> None:
        self.source_commit = "b" * 40
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match requested source commit", result.stderr)


if __name__ == "__main__":
    unittest.main()

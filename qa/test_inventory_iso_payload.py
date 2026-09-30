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

from graphical_payload_fixture import make_graphical_fixture


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
        self.work = self.upstream / "work/tmp.fixture"
        make_graphical_fixture(self.xodus, self.work / "x86_64/airootfs")
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
        subprocess.run(
            [sys.executable, str(self.xodus / "qa/verify-graphical-identity.py"), str(root),
             "--repo-root", str(self.xodus), "--output",
             str(self.upstream / "xodus-graphical-payload-verification.json")],
            check=True, capture_output=True, text=True,
        )

    def enable_welcome(self) -> Path:
        source = self.xodus / "overlay/identity/welcome/xodus-welcome.cpp"
        source.parent.mkdir(parents=True)
        source.write_text("// fixture\n", encoding="utf-8")
        root = self.work / "x86_64/airootfs"
        binary = root / "usr/lib/xodus/xodus-welcome"
        return binary

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
        graphical_path = self.output / "xodus-retained-graphical-payload-verification.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["xodus_source_commit"], self.source_commit)
        self.assertEqual(manifest["iso_sha256"], hashlib.sha256(b"synthetic ISO").hexdigest())
        self.assertEqual(manifest["package_count"], 1)
        self.assertEqual(manifest["license_text_entry_count"], 5)
        self.assertEqual(manifest["wallpaper_entry_count"], 2)
        self.assertEqual(manifest["graphical_identity"]["graphical_identity"], "pass")
        self.assertEqual(manifest["graphical_identity_report_sha256"],
                         hashlib.sha256(graphical_path.read_bytes()).hexdigest())
        self.assertEqual(manifest["graphical_identity"],
                         json.loads(graphical_path.read_text(encoding="utf-8")))
        with package_path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(rows, [{"package": "example", "version": "1.2-3",
                                 "declared_licenses": "MIT"}])
        with asset_path.open(newline="", encoding="utf-8") as stream:
            assets = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual({row["category"] for row in assets},
                         {"license_text", "wallpaper", "ploader_source", "ploader_staged",
                          "ploader_firmware"})
        first = [path.read_bytes() for path in (manifest_path, package_path, asset_path, graphical_path)]
        self.assertEqual(self.run_inventory().returncode, 0)
        self.assertEqual(first, [path.read_bytes() for path in
                                 (manifest_path, package_path, asset_path, graphical_path)])

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

    def test_accepts_staged_m1_welcome(self) -> None:
        self.enable_welcome()
        result = self.run_inventory()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_non_executable_m1_welcome(self) -> None:
        binary = self.enable_welcome()
        binary.chmod(0o644)
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must have mode 0755", result.stderr)

    def test_rejects_missing_m1_welcome(self) -> None:
        self.enable_welcome().unlink()
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("staged Xodus Welcome executable is missing", result.stderr)

    def test_rejects_unmasked_upstream_welcome(self) -> None:
        self.enable_welcome()
        old = self.work / "x86_64/airootfs/usr/share/applications/welcome.desktop"
        old.write_text("[Desktop Entry]\nExec=pearos-welcome\n", encoding="utf-8")
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upstream Welcome entry is not masked", result.stderr)

    def test_rejects_missing_graphical_checker(self) -> None:
        (self.xodus / "qa/verify-graphical-identity.py").unlink()
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("graphical payload checker is missing", result.stderr)
        self.assertFalse((self.output / "xodus-payload-inventory.json").exists())

    def test_rejects_altered_retained_graphics(self) -> None:
        wallpaper = self.work / "x86_64/airootfs/usr/share/wallpapers/Xodus/xodus-wallpaper.png"
        wallpaper.write_bytes(b"changed after build")
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Graphical bytes differ", result.stderr)

    def test_rejects_missing_produced_graphical_evidence(self) -> None:
        (self.upstream / "xodus-graphical-payload-verification.json").unlink()
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("produced ISO graphical verification report is missing", result.stderr)

    def test_rejects_native_app_that_differs_from_produced_iso(self) -> None:
        native = self.work / "x86_64/airootfs/usr/lib/xodus/xodus-settings"
        # Still satisfies the native ELF header and executable contract; only
        # binding to the produced squashfs report detects these changed bytes.
        native.write_bytes(native.read_bytes() + b"changed retained program")
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from produced ISO squashfs", result.stderr)

    def test_rejects_competing_login_selection(self) -> None:
        selection = self.work / "x86_64/airootfs/etc/sddm.conf.d/99-other.conf"
        selection.write_text("[Theme]\nCurrent=pearOS\n", encoding="utf-8")
        result = self.run_inventory()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Competing SDDM", result.stderr)


if __name__ == "__main__":
    unittest.main()

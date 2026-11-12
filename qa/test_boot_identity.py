"""Boot source drift, retained-byte and default-theme release contracts."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from boot_identity_fixture import make_fixture


REPO = Path(__file__).resolve().parents[1]
BOOT = REPO / "overlay/identity/boot"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


apply = load("boot_apply", BOOT / "apply-boot-identity.py")
verify = load("boot_verify", BOOT / "verify-boot-identity.py")


class BootIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xodus-boot-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "source"
        make_fixture(self.root)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file() and not p.is_symlink()}

    def assert_rejected_without_writes(self, message):
        before = self.snapshot()
        with self.assertRaisesRegex(SystemExit, message):
            apply.transform(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_source_transform_passes_retained_boot_contract(self):
        apply.transform(self.root)
        hashes = verify.asset_hashes()
        verify.source_root(self.root, hashes)
        self.assertEqual(len(list((self.root / "pear/airootfs/usr/share/plymouth/themes/xodus")
                                  .glob("frame-*.png"))), 241)
        customize = (self.root / "pear/airootfs/root/customize_airootfs.sh").read_text()
        self.assertIn('[[ "$(plymouth-set-default-theme)" == xodus ]]', customize)
        self.assertNotIn("Failed to set plymouth theme", customize)

    def test_late_grub_source_drift_aborts_before_firmware_changes(self):
        path = self.root / "pear/airootfs/etc/default/grub"
        path.write_text(path.read_text().replace('GRUB_DISTRIBUTOR="Arch"', 'GRUB_DISTRIBUTOR="Other"'))
        self.assert_rejected_without_writes("GRUB distributor")

    def test_live_initramfs_without_plymouth_aborts_before_changes(self):
        path = self.root / "pear/airootfs/etc/mkinitcpio.conf"
        path.write_text(path.read_text().replace(" plymouth ", " "))
        self.assert_rejected_without_writes("initramfs no longer includes Plymouth")

    def test_missing_ventoy_entry_aborts_before_changes(self):
        (self.root / "pear/efiboot/loader/entries/03-archiso-x86_64-linux-legacy.conf").unlink()
        self.assert_rejected_without_writes("missing or unsafe")

    def test_approved_master_hash_cannot_drift(self):
        master = self.root / "changed.mp4"
        master.write_bytes(b"changed video")
        with patch.object(apply, "MASTER", master):
            self.assert_rejected_without_writes("approved video master is missing or changed")

    def test_staged_theme_selection_cannot_restore_pear_theme(self):
        apply.transform(self.root)
        live = self.root / "pear/airootfs"
        conf = live / "etc/plymouth/plymouthd.conf"
        conf.parent.mkdir(parents=True)
        conf.write_text("[Daemon]\nTheme=pear-plymouth\n")
        with self.assertRaisesRegex(ValueError, "default theme is not xodus"):
            verify.selected_theme(live)
        conf.write_text("[Daemon]\nTheme=xodus\n")
        verify.selected_theme(live)

    def test_last_retained_animation_frame_is_required(self):
        apply.transform(self.root)
        live = self.root / "pear/airootfs"
        (live / "usr/share/plymouth/themes/xodus/frame-240.png").unlink()
        with self.assertRaisesRegex(ValueError, "missing or unreviewed frames"):
            verify.theme(live, verify.asset_hashes())

    def test_retained_artwork_is_verified_by_checksum(self):
        apply.transform(self.root)
        (self.root / "pear/efiboot/ploader/theme/bg/background.png").write_bytes(b"wrong artwork")
        with self.assertRaisesRegex(ValueError, "differs from approved export"):
            verify.firmware(self.root, "pear/efiboot/ploader", verify.asset_hashes())

    def test_single_combined_initrd_and_debug_paths_survive_rebrand(self):
        original = (self.root / "pear/efiboot/ploader/ploader.conf").read_text()
        apply.transform(self.root)
        branded = (self.root / "pear/efiboot/ploader/ploader.conf").read_text()
        self.assertEqual([line for line in original.splitlines() if line.strip().startswith(("loader ", "initrd ", "options "))],
                         [line for line in branded.splitlines() if line.strip().startswith(("loader ", "initrd ", "options "))])

    @unittest.skipIf(__import__("os").name == "nt", "Linux symlink safety contract")
    def test_symlinked_source_path_cannot_escape_checkout(self):
        outside = Path(self.temp.name) / "outside"
        outside.write_text("unrelated data")
        path = self.root / "pear/airootfs/usr/local/bin/alg-finalisation"
        path.unlink()
        path.symlink_to(outside)
        self.assert_rejected_without_writes("missing or unsafe")
        self.assertEqual(outside.read_text(), "unrelated data")


if __name__ == "__main__":
    unittest.main()

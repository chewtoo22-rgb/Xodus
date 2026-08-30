#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name("first-boot-runtime-acceptance.py")
spec = importlib.util.spec_from_file_location("acceptance", MODULE_PATH)
acceptance = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(acceptance)

class AcceptanceTests(unittest.TestCase):
    def fixture(self, *, firmware="uefi", fstype="ext4", source="/dev/nvme0n1p2",
                complete_ts="2026-08-30T10:00:00Z", system_ts=None,
                tier="standard", backend="cpu"):
        td = tempfile.TemporaryDirectory()
        root = pathlib.Path(td.name)
        fb = root / "var/lib/xodus/first-boot"
        ai = root / "var/lib/xodus/ai"
        fb.mkdir(parents=True)
        ai.mkdir(parents=True)
        system_ts = system_ts or complete_ts
        (fb / "complete").write_text(f"schema=1\ncompleted_utc={complete_ts}\n", encoding="utf-8")
        (fb / "system.env").write_text(
            "\n".join([
                "XODUS_FIRST_BOOT_SCHEMA=1",
                f"XODUS_FIRST_BOOT_COMPLETED_UTC={system_ts}",
                f"XODUS_ROOT_SOURCE={source}",
                f"XODUS_ROOT_FSTYPE={fstype}",
                f"XODUS_FIRMWARE={firmware}",
                "XODUS_UPSTREAM_COMMIT=unknown",
                "",
            ]),
            encoding="utf-8",
        )
        selection = {
            "hardware": {"ram_gib": 32, "vram_gib": 0, "gpu_vendor": "intel", "cpu_threads": 16},
            "recommendation": {
                "tier": tier,
                "max_model_class": "nano",
                "preferred_quant": "q4_k_m",
                "backend": backend,
                "reason": "fixture",
            },
        }
        (ai / "hardware-selection.json").write_text(json.dumps(selection), encoding="utf-8")
        return td, root

    def test_accepts_coherent_installed_uefi_state(self):
        td, root = self.fixture()
        self.addCleanup(td.cleanup)
        result = acceptance.validate(root)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["ai_tier"], "standard")
        self.assertFalse(result["hardware_validation_claim"])

    def test_rejects_bios(self):
        td, root = self.fixture(firmware="bios")
        self.addCleanup(td.cleanup)
        with self.assertRaisesRegex(ValueError, "requires UEFI"):
            acceptance.validate(root)

    def test_rejects_live_root(self):
        td, root = self.fixture(fstype="squashfs", source="/dev/loop0")
        self.addCleanup(td.cleanup)
        with self.assertRaisesRegex(ValueError, "live/ephemeral"):
            acceptance.validate(root)

    def test_rejects_timestamp_disagreement(self):
        td, root = self.fixture(system_ts="2026-08-30T10:01:00Z")
        self.addCleanup(td.cleanup)
        with self.assertRaisesRegex(ValueError, "timestamps disagree"):
            acceptance.validate(root)

    def test_rejects_symlinked_selection(self):
        td, root = self.fixture()
        self.addCleanup(td.cleanup)
        selection = root / "var/lib/xodus/ai/hardware-selection.json"
        real = selection.with_suffix(".real")
        selection.replace(real)
        selection.symlink_to(real)
        with self.assertRaisesRegex(ValueError, "symlink not allowed"):
            acceptance.validate(root)

    def test_rejects_enabled_tier_without_backend(self):
        td, root = self.fixture(tier="standard", backend="none")
        self.addCleanup(td.cleanup)
        with self.assertRaisesRegex(ValueError, "enabled AI tier"):
            acceptance.validate(root)

    def test_accepts_disabled_tier_with_none_backend(self):
        td, root = self.fixture(tier="disabled", backend="none")
        self.addCleanup(td.cleanup)
        result = acceptance.validate(root)
        self.assertEqual(result["ai_tier"], "disabled")
        self.assertEqual(result["ai_backend"], "none")

    def test_rejects_duplicate_complete_key(self):
        td, root = self.fixture()
        self.addCleanup(td.cleanup)
        complete = root / "var/lib/xodus/first-boot/complete"
        complete.write_text(
            "schema=1\ncompleted_utc=2026-08-30T10:00:00Z\nschema=1\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "duplicate/empty key"):
            acceptance.validate(root)

if __name__ == "__main__":
    unittest.main()

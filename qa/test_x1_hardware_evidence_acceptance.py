#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("x1-hardware-evidence-acceptance.py")
spec = importlib.util.spec_from_file_location("x1_acceptance", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

SHA = "a" * 40


class AcceptanceTests(unittest.TestCase):
    def valid_live(self):
        return {"collector": "pass", "candidate_sha": SHA}

    def valid_installed(self):
        return {
            "collector": "pass",
            "candidate_sha": SHA,
            "boot_mode": "uefi",
            "root_source": "/dev/nvme0n1p2",
            "root_fstype": "ext4",
            "root_backing_disk": "/dev/nvme0n1",
            "physical_install_claim": "not_automatic",
        }

    def test_accepts_complete_matching_evidence_without_claiming_validation(self):
        result = module.evaluate(SHA, self.valid_live(), self.valid_installed())
        self.assertTrue(result["evidence_ready_for_operator_review"])
        self.assertFalse(result["hardware_validation_claim"])
        self.assertEqual([], result["blockers"])

    def test_rejects_candidate_mismatch(self):
        live = self.valid_live()
        live["candidate_sha"] = "b" * 40
        result = module.evaluate(SHA, live, self.valid_installed())
        self.assertFalse(result["evidence_ready_for_operator_review"])
        self.assertIn("live_candidate_sha_mismatch", result["blockers"])

    def test_rejects_live_or_overlay_installed_root(self):
        installed = self.valid_installed()
        installed["root_fstype"] = "squashfs"
        result = module.evaluate(SHA, self.valid_live(), installed)
        self.assertIn("installed_root_looks_live", result["blockers"])

    def test_rejects_missing_backing_disk_and_unsafe_claim(self):
        installed = self.valid_installed()
        installed["root_backing_disk"] = "unknown"
        installed["physical_install_claim"] = "pass"
        result = module.evaluate(SHA, self.valid_live(), installed)
        self.assertIn("installed_backing_disk_missing", result["blockers"])
        self.assertIn("unsafe_physical_install_claim", result["blockers"])

    def test_rejects_invalid_candidate_sha(self):
        result = module.evaluate("main", self.valid_live(), self.valid_installed())
        self.assertIn("candidate_sha_invalid", result["blockers"])

    def test_summary_parser_rejects_duplicate_keys_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate = root / "summary.txt"
            duplicate.write_text("collector=pass\ncollector=pass\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                module.read_summary(duplicate)
            target = root / "target.txt"
            target.write_text("collector=pass\n", encoding="utf-8")
            link = root / "link.txt"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                module.read_summary(link)


if __name__ == "__main__":
    unittest.main()

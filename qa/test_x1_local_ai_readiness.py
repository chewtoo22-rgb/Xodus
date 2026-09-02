#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name("x1-local-ai-readiness.py")
spec = importlib.util.spec_from_file_location("x1_local_ai_readiness", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

SHA = "a" * 40


def nuc(**overrides):
    value = {
        "schema": 1, "status": "ready_for_nuc_hardware_test", "candidate_sha": SHA,
        "boot_mode": "uefi", "root_source": "/dev/nvme0n1p2", "root_fstype": "ext4",
        "root_backing_disk": "/dev/nvme0n1", "first_boot_completed_utc": "2026-08-30T15:00:00Z",
        "ai_tier": "standard", "ai_backend": "cpu", "physical_install_claim": "not_automatic",
        "hardware_validation_claim": False,
    }
    value.update(overrides)
    return value


def runtime(**overrides):
    value = {
        "schema": 1, "ready": True, "hardware_validation_claim": False, "network_used": False,
        "tier": "standard", "backend": "cpu", "engine": "/usr/bin/llama-cli",
        "blockers": [], "warnings": [],
    }
    value.update(overrides)
    return value


class ReadinessTests(unittest.TestCase):
    def write(self, root, name, value):
        path = pathlib.Path(root) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def validate(self, n, r):
        with tempfile.TemporaryDirectory() as td:
            return mod.validate(self.write(td, "nuc.json", n), self.write(td, "runtime.json", r))

    def test_accepts_coherent_offline_runtime(self):
        out = self.validate(nuc(), runtime())
        self.assertEqual(out["status"], "ready_for_nuc_local_ai_test")
        self.assertEqual(out["candidate_sha"], SHA)
        self.assertFalse(out["network_used"])
        self.assertFalse(out["hardware_validation_claim"])

    def test_rejects_runtime_not_ready(self):
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.validate(nuc(), runtime(ready=False, blockers=["llama_cpp_runtime_missing"], engine=None))

    def test_rejects_tier_or_backend_drift(self):
        with self.assertRaisesRegex(ValueError, "tier disagrees"):
            self.validate(nuc(), runtime(tier="lite"))
        with self.assertRaisesRegex(ValueError, "backend disagrees"):
            self.validate(nuc(), runtime(backend="vulkan"))

    def test_rejects_network_or_claim_drift(self):
        with self.assertRaisesRegex(ValueError, "offline"):
            self.validate(nuc(), runtime(network_used=True))
        with self.assertRaisesRegex(ValueError, "must not claim"):
            self.validate(nuc(), runtime(hardware_validation_claim=True))

    def test_rejects_ready_with_blockers(self):
        with self.assertRaisesRegex(ValueError, "cannot contain blockers"):
            self.validate(nuc(), runtime(blockers=["unexpected"]))

    def test_rejects_disabled_policy_and_relative_engine(self):
        with self.assertRaisesRegex(ValueError, "disables"):
            self.validate(nuc(ai_tier="disabled", ai_backend="none"), runtime(tier="disabled", backend="none"))
        with self.assertRaisesRegex(ValueError, "absolute path"):
            self.validate(nuc(), runtime(engine="llama-cli"))

    def test_rejects_schema_drift_and_symlink_evidence(self):
        with self.assertRaisesRegex(ValueError, "unexpected local AI runtime schema"):
            self.validate(nuc(), {**runtime(), "extra": True})
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            target = self.write(td, "runtime-real.json", runtime())
            link = root / "runtime.json"
            link.symlink_to(target)
            npath = self.write(td, "nuc.json", nuc())
            with self.assertRaisesRegex(ValueError, "symlink not allowed"):
                mod.validate(npath, link)

    def test_publishes_new_evidence_without_temp_residue(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            out = root / "local-ai.json"
            mod.publish_evidence(out, "{\"status\":\"ok\"}\n")
            self.assertEqual(out.read_text(encoding="utf-8"), "{\"status\":\"ok\"}\n")
            self.assertEqual(list(root.glob(".local-ai.json.*.tmp")), [])

    def test_refuses_existing_output_without_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            out = root / "local-ai.json"
            out.write_text("original\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                mod.publish_evidence(out, "replacement\n")
            self.assertEqual(out.read_text(encoding="utf-8"), "original\n")

    def test_refuses_missing_or_symlink_parent(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            missing = root / "missing" / "local-ai.json"
            with self.assertRaisesRegex(ValueError, "existing non-symlink directory"):
                mod.publish_evidence(missing, "evidence\n")
            self.assertFalse(missing.parent.exists())

            real_parent = root / "real"
            real_parent.mkdir()
            link_parent = root / "linked"
            link_parent.symlink_to(real_parent, target_is_directory=True)
            redirected = link_parent / "local-ai.json"
            with self.assertRaisesRegex(ValueError, "existing non-symlink directory"):
                mod.publish_evidence(redirected, "evidence\n")
            self.assertFalse((real_parent / "local-ai.json").exists())

    def test_refuses_symlink_output_without_touching_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            target = root / "target.json"
            target.write_text("original\n", encoding="utf-8")
            out = root / "local-ai.json"
            out.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "already exists"):
                mod.publish_evidence(out, "replacement\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "original\n")


if __name__ == "__main__":
    unittest.main()

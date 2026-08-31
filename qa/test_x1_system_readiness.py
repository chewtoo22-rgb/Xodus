#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name("x1-system-readiness.py")
spec = importlib.util.spec_from_file_location("x1_system_readiness", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

SHA = "a" * 40


def local_ai(**updates):
    value = {
        "schema": 1,
        "status": "ready_for_nuc_local_ai_test",
        "candidate_sha": SHA,
        "ai_tier": "standard",
        "ai_backend": "cpu",
        "engine": "/usr/bin/llama-server",
        "network_used": False,
        "physical_install_claim": "not_automatic",
        "hardware_validation_claim": False,
    }
    value.update(updates)
    return value


def desktop(**updates):
    value = {
        "schema": "1",
        "hardware_validation_claim": "false",
        "desktop_ready": "true",
        "blockers": "",
        "warnings": "",
    }
    value.update(updates)
    return value


class X1SystemReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.ai = self.root / "local-ai.json"
        self.desktop = self.root / "desktop.txt"

    def tearDown(self):
        self.tmp.cleanup()

    def write_ai(self, value):
        self.ai.write_text(json.dumps(value), encoding="utf-8")

    def write_desktop(self, value):
        self.desktop.write_text(
            "".join(f"{key}={item}\n" for key, item in value.items()),
            encoding="utf-8",
        )

    def validate(self):
        return mod.validate(self.ai, self.desktop)

    def test_ready_bundle_passes_and_preserves_warnings(self):
        self.write_ai(local_ai())
        self.write_desktop(desktop(warnings="pipewire_not_detected,xdg_open_not_detected"))
        result = self.validate()
        self.assertEqual(result["status"], "ready_for_x1_nuc_system_test")
        self.assertEqual(result["candidate_sha"], SHA)
        self.assertTrue(result["desktop_ready"])
        self.assertEqual(
            result["desktop_warnings"],
            ["pipewire_not_detected", "xdg_open_not_detected"],
        )
        self.assertFalse(result["hardware_validation_claim"])
        self.assertFalse(result["network_used"])

    def test_desktop_not_ready_fails(self):
        self.write_ai(local_ai())
        self.write_desktop(desktop(desktop_ready="false", blockers="no_desktop_session"))
        with self.assertRaisesRegex(ValueError, "desktop preflight is not ready"):
            self.validate()

    def test_ready_desktop_with_blocker_fails(self):
        self.write_ai(local_ai())
        self.write_desktop(desktop(blockers="display_manager_not_enabled"))
        with self.assertRaisesRegex(ValueError, "cannot contain blockers"):
            self.validate()

    def test_local_ai_hardware_claim_fails(self):
        self.write_ai(local_ai(hardware_validation_claim=True))
        self.write_desktop(desktop())
        with self.assertRaisesRegex(ValueError, "must not claim hardware validation"):
            self.validate()

    def test_network_use_fails(self):
        self.write_ai(local_ai(network_used=True))
        self.write_desktop(desktop())
        with self.assertRaisesRegex(ValueError, "remain offline"):
            self.validate()

    def test_disabled_ai_policy_fails(self):
        self.write_ai(local_ai(ai_tier="disabled", ai_backend="none"))
        self.write_desktop(desktop())
        with self.assertRaisesRegex(ValueError, "disabled hardware policy"):
            self.validate()

    def test_schema_drift_fails(self):
        value = local_ai()
        value["extra"] = True
        self.write_ai(value)
        self.write_desktop(desktop())
        with self.assertRaisesRegex(ValueError, "unexpected local AI readiness schema"):
            self.validate()

    def test_duplicate_desktop_key_fails(self):
        self.write_ai(local_ai())
        self.desktop.write_text(
            "schema=1\nhardware_validation_claim=false\ndesktop_ready=true\n"
            "blockers=\nwarnings=\nwarnings=duplicate\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "duplicate/empty key"):
            self.validate()

    def test_symlink_evidence_fails(self):
        real = self.root / "real-ai.json"
        real.write_text(json.dumps(local_ai()), encoding="utf-8")
        self.ai.symlink_to(real)
        self.write_desktop(desktop())
        with self.assertRaisesRegex(ValueError, "symlink not allowed"):
            self.validate()

    def test_output_symlink_fails_without_touching_target(self):
        target = self.root / "target.json"
        target.write_text("preserve-me\n", encoding="utf-8")
        out = self.root / "system-readiness.json"
        out.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "output symlink not allowed"):
            mod.write_output(out, "replacement\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "preserve-me\n")

    def test_output_parent_symlink_fails(self):
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        out = linked_parent / "system-readiness.json"
        with self.assertRaisesRegex(ValueError, "output parent symlink not allowed"):
            mod.write_output(out, "payload\n")
        self.assertFalse((real_parent / "system-readiness.json").exists())

    def test_output_directory_fails_closed(self):
        out = self.root / "system-readiness.json"
        out.mkdir()
        with self.assertRaisesRegex(ValueError, "output must be a regular file"):
            mod.write_output(out, "payload\n")

    def test_output_atomic_replace_leaves_no_predictable_temp(self):
        out = self.root / "system-readiness.json"
        out.write_text("old\n", encoding="utf-8")
        mod.write_output(out, "new\n")
        self.assertEqual(out.read_text(encoding="utf-8"), "new\n")
        leftovers = list(self.root.glob(".system-readiness.json.*.tmp"))
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()

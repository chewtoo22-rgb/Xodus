#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "xodus-ai-launch-plan.py"
spec = importlib.util.spec_from_file_location("xodus_ai_launch_plan", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class LaunchPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.readiness = self.root / "readiness.json"
        self.model = self.root / "model.gguf"
        self.model.write_bytes(b"GGUF-test-model")
        self.base = {
            "schema": 1,
            "status": "ready_for_nuc_local_ai_test",
            "candidate_sha": "a" * 40,
            "ai_tier": "standard",
            "ai_backend": "cpu",
            "engine": "/usr/bin/llama-server",
            "network_used": False,
            "physical_install_claim": "not_automatic",
            "hardware_validation_claim": False,
        }
        self.write_readiness(self.base)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_readiness(self, value: dict) -> None:
        self.readiness.write_text(json.dumps(value), encoding="utf-8")

    def load(self) -> dict:
        return module.load_readiness(self.readiness)

    def test_standard_plan_is_loopback_only_and_nonexecuting(self) -> None:
        plan = module.build_plan(self.load(), self.model, "127.0.0.1", 11435)
        self.assertEqual(plan["status"], "ready_for_local_launch")
        self.assertEqual(plan["context_tokens"], 8192)
        self.assertEqual(plan["argv"], [
            "/usr/bin/llama-server", "--model", str(self.model),
            "--host", "127.0.0.1", "--port", "11435",
            "--ctx-size", "8192",
        ])
        self.assertFalse(plan["network_downloads_allowed"])
        self.assertFalse(plan["mutates_system"])
        self.assertFalse(plan["executes_process"])
        self.assertFalse(plan["hardware_validation_claim"])
        self.assertEqual(len(plan["model_sha256"]), 64)

    def test_llama_cli_is_not_server_launchable(self) -> None:
        value = dict(self.base)
        value["engine"] = "/usr/bin/llama-cli"
        self.write_readiness(value)
        with self.assertRaisesRegex(ValueError, "llama-server"):
            self.load()

    def test_remote_bind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            module.build_plan(self.load(), self.model, "0.0.0.0", 11435)

    def test_privileged_and_invalid_ports_are_rejected(self) -> None:
        for port in (0, 80, 65536):
            with self.subTest(port=port):
                with self.assertRaisesRegex(ValueError, "port"):
                    module.build_plan(self.load(), self.model, "127.0.0.1", port)

    def test_symlink_model_is_rejected(self) -> None:
        link = self.root / "linked.gguf"
        link.symlink_to(self.model)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            module.build_plan(self.load(), link, "127.0.0.1", 11435)

    def test_non_gguf_model_is_rejected(self) -> None:
        other = self.root / "model.bin"
        other.write_bytes(b"model")
        with self.assertRaisesRegex(ValueError, "GGUF"):
            module.build_plan(self.load(), other, "127.0.0.1", 11435)

    def test_candidate_sha_drift_is_rejected(self) -> None:
        value = dict(self.base)
        value["candidate_sha"] = "A" * 40
        self.write_readiness(value)
        with self.assertRaisesRegex(ValueError, "candidate SHA"):
            self.load()

    def test_unknown_readiness_fields_are_rejected(self) -> None:
        value = dict(self.base)
        value["surprise"] = True
        self.write_readiness(value)
        with self.assertRaisesRegex(ValueError, "schema"):
            self.load()

    def test_hardware_claim_escalation_is_rejected(self) -> None:
        value = dict(self.base)
        value["hardware_validation_claim"] = True
        self.write_readiness(value)
        with self.assertRaisesRegex(ValueError, "hardware-validation"):
            self.load()

    def test_tier_controls_context_deterministically(self) -> None:
        expected = {"lite": 4096, "standard": 8192, "performance": 16384, "workstation": 32768}
        for tier, ctx in expected.items():
            with self.subTest(tier=tier):
                value = dict(self.base)
                value["ai_tier"] = tier
                self.write_readiness(value)
                plan = module.build_plan(self.load(), self.model, "::1", 22000)
                self.assertEqual(plan["context_tokens"], ctx)
                self.assertEqual(plan["bind_host"], "::1")

    def test_publish_plan_creates_new_durable_artifact(self) -> None:
        out = self.root / "launch.json"
        payload = '{"status":"ready_for_local_launch"}\n'
        module.publish_plan(out, payload)
        self.assertEqual(out.read_text(encoding="utf-8"), payload)
        self.assertFalse(any(self.root.glob(".launch.json.*.tmp")))

    def test_publish_plan_refuses_existing_or_symlink_output(self) -> None:
        existing = self.root / "existing.json"
        existing.write_text("old", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            module.publish_plan(existing, "new\n")
        self.assertEqual(existing.read_text(encoding="utf-8"), "old")

        target = self.root / "target.json"
        target.write_text("target", encoding="utf-8")
        link = self.root / "linked.json"
        link.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "already exists"):
            module.publish_plan(link, "new\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "target")

    def test_publish_plan_rejects_symlink_parent(self) -> None:
        real_parent = self.root / "real"
        real_parent.mkdir()
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "non-symlink directory"):
            module.publish_plan(linked_parent / "launch.json", "new\n")
        self.assertFalse((real_parent / "launch.json").exists())

    def test_publish_plan_cleans_temp_file_on_replace_failure(self) -> None:
        out = self.root / "launch.json"
        with mock.patch.object(module.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                module.publish_plan(out, "payload\n")
        self.assertFalse(out.exists())
        self.assertFalse(any(self.root.glob(".launch.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()

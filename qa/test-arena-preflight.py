#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "xodus-arena-preflight"


def snapshot(**overrides):
    data = {
        "schema": 1,
        "session": "wayland",
        "gpu_vendors": ["intel"],
        "tools": {},
        "services": {},
        "arena": {
            "session_ready": True,
            "steam_ready": True,
            "performance_profile_ready": True,
            "audio_policy_ready": True,
            "telemetry_ready": True,
        },
        "graphics": {},
        "policy": {
            "read_only_probe": True,
            "unsupported_features_hidden": True,
            "hardware_validation_claim": False,
        },
    }
    for key, value in overrides.items():
        if key.startswith("arena_"):
            data["arena"][key.removeprefix("arena_")] = value
        elif key.startswith("policy_"):
            data["policy"][key.removeprefix("policy_")] = value
        else:
            data[key] = value
    return data


def run(data, *args):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "snapshot.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        proc = subprocess.run(
            ["python3", str(SCRIPT), "--snapshot", str(path), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return proc.returncode, json.loads(proc.stdout)


class ArenaPreflightTests(unittest.TestCase):
    def test_ready_snapshot_authorizes_launch(self):
        code, result = run(snapshot())
        self.assertEqual(code, 0)
        self.assertTrue(result["ready"])
        self.assertTrue(result["policy"]["launch_authorized"])
        self.assertFalse(result["policy"]["state_changes_performed"])

    def test_gamescope_is_required(self):
        code, result = run(snapshot(arena_session_ready=False))
        self.assertEqual(code, 1)
        self.assertEqual(result["blockers"], ["gamescope_unavailable"])

    def test_unknown_only_gpu_fails_closed(self):
        code, result = run(snapshot(gpu_vendors=["unknown"]))
        self.assertEqual(code, 1)
        self.assertIn("gpu_not_identified", result["blockers"])

    def test_optional_tools_warn_without_blocking(self):
        code, result = run(snapshot(
            arena_audio_policy_ready=False,
            arena_performance_profile_ready=False,
            arena_telemetry_ready=False,
            arena_steam_ready=False,
        ))
        self.assertEqual(code, 0)
        self.assertTrue(result["ready"])
        self.assertEqual(result["warnings"], sorted([
            "audio_policy_unavailable",
            "performance_profile_unavailable",
            "steam_unavailable",
            "telemetry_unavailable",
        ]))

    def test_steam_can_be_required_by_session_policy(self):
        code, result = run(snapshot(arena_steam_ready=False), "--require-steam")
        self.assertEqual(code, 1)
        self.assertEqual(result["blockers"], ["steam_unavailable"])

    def test_invalid_schema_fails_closed(self):
        code, result = run(snapshot(schema=99))
        self.assertEqual(code, 2)
        self.assertFalse(result["ready"])
        self.assertEqual(result["blockers"], ["invalid_capability_snapshot"])

    def test_non_read_only_source_is_rejected(self):
        code, result = run(snapshot(policy_read_only_probe=False))
        self.assertEqual(code, 2)
        self.assertFalse(result["policy"]["launch_authorized"])

    def test_hardware_claim_is_rejected(self):
        code, result = run(snapshot(policy_hardware_validation_claim=True))
        self.assertEqual(code, 2)
        self.assertFalse(result["ready"])

    def test_mixed_known_and_unknown_gpu_warns(self):
        code, result = run(snapshot(gpu_vendors=["unknown", "intel"]))
        self.assertEqual(code, 0)
        self.assertEqual(result["gpu_vendors"], ["intel"])
        self.assertIn("additional_unknown_gpu_present", result["warnings"])


if __name__ == "__main__":
    unittest.main()

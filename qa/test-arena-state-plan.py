#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("arena_state_plan", ROOT / "scripts" / "arena-state-plan.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["arena_state_plan"] = mod
SPEC.loader.exec_module(mod)


class ArenaStatePlanTests(unittest.TestCase):
    def snapshot(self, **overrides):
        value = {
            "schema": 1,
            "power_profile": "balanced",
            "audio_profile": "default",
            "maintenance_paused": False,
            "ai_runtime": "active",
        }
        value.update(overrides)
        return value

    def request(self, **overrides):
        value = {"schema": 1, "arena_profile": "performance", "yield_ai": True}
        value.update(overrides)
        return value

    def test_performance_plan_is_reversible(self):
        result = mod.plan(self.snapshot(), self.request())
        self.assertFalse(result["mutates_system"])
        self.assertFalse(result["hardware_validation_claim"])
        self.assertEqual(
            result["enter"],
            [
                {"set": "power_profile", "from": "balanced", "to": "performance"},
                {"set": "audio_profile", "from": "default", "to": "low-latency"},
                {"set": "maintenance_paused", "from": False, "to": True},
                {"set": "ai_runtime", "from": "active", "to": "yielded"},
            ],
        )
        self.assertEqual(result["restore"], [
            {"set": "ai_runtime", "from": "yielded", "to": "active"},
            {"set": "maintenance_paused", "from": True, "to": False},
            {"set": "audio_profile", "from": "low-latency", "to": "default"},
            {"set": "power_profile", "from": "performance", "to": "balanced"},
        ])

    def test_quiet_profile_only_changes_needed_fields(self):
        result = mod.plan(self.snapshot(ai_runtime="yielded"), self.request(arena_profile="quiet", yield_ai=False))
        self.assertEqual(result["enter"], [{"set": "power_profile", "from": "balanced", "to": "power-saver"}])
        self.assertEqual(result["restore"], [{"set": "power_profile", "from": "power-saver", "to": "balanced"}])

    def test_unknown_snapshot_field_rejected(self):
        with self.assertRaises(mod.ContractError):
            mod.plan(self.snapshot(extra=True), self.request())

    def test_unknown_request_field_rejected(self):
        with self.assertRaises(mod.ContractError):
            mod.plan(self.snapshot(), self.request(extra=True))

    def test_bad_schema_rejected(self):
        with self.assertRaises(mod.ContractError):
            mod.plan(self.snapshot(schema=2), self.request())

    def test_bad_profile_rejected(self):
        with self.assertRaises(mod.ContractError):
            mod.plan(self.snapshot(), self.request(arena_profile="turbo"))

    def test_non_boolean_yield_rejected(self):
        with self.assertRaises(mod.ContractError):
            mod.plan(self.snapshot(), self.request(yield_ai=1))

    def test_unsupported_snapshot_state_rejected(self):
        with self.assertRaises(mod.ContractError):
            mod.plan(self.snapshot(power_profile="extreme"), self.request())


if __name__ == "__main__":
    unittest.main()

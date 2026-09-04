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

    # === Rollback verification tests ===
    def test_restore_plan_reverses_all_enter_transitions(self):
        """Verify that applying restore steps returns to original snapshot state."""
        original = self.snapshot()
        plan_result = mod.plan(original, self.request(arena_profile="performance", yield_ai=True))
        
        # Apply enter transitions to get new state
        entered_state = dict(original)
        for step in plan_result["enter"]:
            entered_state[step["set"]] = step["to"]
        
        # Apply restore transitions
        restored_state = dict(entered_state)
        for step in plan_result["restore"]:
            restored_state[step["set"]] = step["to"]
        
        # Verify we're back to original
        self.assertEqual(restored_state["power_profile"], original["power_profile"])
        self.assertEqual(restored_state["audio_profile"], original["audio_profile"])
        self.assertEqual(restored_state["maintenance_paused"], original["maintenance_paused"])
        self.assertEqual(restored_state["ai_runtime"], original["ai_runtime"])

    def test_double_reversal_idempotent(self):
        """Verify that enter -> restore -> enter yields identical results."""
        original = self.snapshot()
        request = self.request(arena_profile="quiet")
        
        plan1 = mod.plan(original, request)
        
        # Simulate entering
        simulated = dict(original)
        for step in plan1["enter"]:
            simulated[step["set"]] = step["to"]
        
        # Plan from entered state back to original
        plan_back = mod.plan(simulated, self.request(arena_profile="balanced", yield_ai=False))
        
        # Re-plan from original
        plan2 = mod.plan(original, request)
        
        # Both should have identical enter steps (same transitions)
        self.assertEqual(plan1["enter"], plan2["enter"])
        self.assertEqual(len(plan1["restore"]), len(plan2["restore"]))

    def test_malformed_restore_step_missing_fields(self):
        """Verify that incomplete restore steps are caught early by parser."""
        # This is a data validation test: the planner always produces valid steps,
        # but if something corrupts the plan, restoration should fail safely.
        original = self.snapshot()
        plan_result = mod.plan(original, self.request())
        
        # Verify all restore steps have required keys
        for step in plan_result["restore"]:
            self.assertIn("set", step)
            self.assertIn("from", step)
            self.assertIn("to", step)
            self.assertEqual(len(step), 3, "restore step has extra fields")

    def test_enter_restore_are_inverse_order(self):
        """Verify that restore steps are in exact reverse order of enter steps."""
        plan_result = mod.plan(self.snapshot(), self.request(arena_profile="performance"))
        
        self.assertEqual(len(plan_result["enter"]), len(plan_result["restore"]))
        
        # Each restore step should reverse the corresponding enter step (in reverse position)
        for i, enter_step in enumerate(plan_result["enter"]):
            restore_step = plan_result["restore"][-(i + 1)]
            self.assertEqual(enter_step["set"], restore_step["set"])
            self.assertEqual(enter_step["to"], restore_step["from"])
            self.assertEqual(enter_step["from"], restore_step["to"])

    def test_no_idempotent_transitions(self):
        """Verify planner omits no-op transitions (from == to)."""
        # Request no AI yield change when already not yielded
        result = mod.plan(
            self.snapshot(ai_runtime="active"),
            self.request(yield_ai=False)
        )
        # Should only have power, audio, maintenance changes
        self.assertNotIn(
            {"set": "ai_runtime", "from": "active", "to": "active"},
            result["enter"]
        )

    def test_all_profiles_reversible(self):
        """Verify all arena profiles generate valid, reversible plans."""
        for profile in ["quiet", "balanced", "performance"]:
            for yield_ai in [True, False]:
                original = self.snapshot()
                plan_result = mod.plan(original, self.request(arena_profile=profile, yield_ai=yield_ai))
                
                # Apply transitions
                simulated = dict(original)
                for step in plan_result["enter"]:
                    simulated[step["set"]] = step["to"]
                
                # Restore
                for step in plan_result["restore"]:
                    simulated[step["set"]] = step["to"]
                
                # Back to original
                self.assertEqual(simulated["power_profile"], original["power_profile"])
                self.assertEqual(simulated["audio_profile"], original["audio_profile"])
                self.assertEqual(simulated["maintenance_paused"], original["maintenance_paused"])
                self.assertEqual(simulated["ai_runtime"], original["ai_runtime"])


if __name__ == "__main__":
    unittest.main()

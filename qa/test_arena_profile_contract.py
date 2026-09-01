#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).with_name("arena_profile_contract.py")
spec = importlib.util.spec_from_file_location("arena_profile_contract", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class ArenaProfileContractTests(unittest.TestCase):
    def base(self, profile="balanced"):
        return {"schema_version": 1, "profile": profile}

    def test_defaults_are_deterministic_and_nonexecuting(self):
        admitted = mod.admit_profile(self.base())
        self.assertEqual(admitted.cpu_governor, "schedutil")
        self.assertEqual(admitted.frame_limit_hz, 120)
        self.assertTrue(admitted.local_ai_yield)
        self.assertFalse(admitted.mutates_system)
        self.assertFalse(admitted.executes_process)
        self.assertFalse(admitted.hardware_validation_claim)

    def test_unknown_field_is_rejected(self):
        raw = self.base()
        raw["shell"] = "rm -rf /"
        with self.assertRaises(mod.ArenaProfileError):
            mod.admit_profile(raw)

    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(mod.ArenaProfileError):
            mod.admit_profile(self.base("turbo-forever"))

    def test_refresh_bounds_are_enforced(self):
        raw = self.base()
        raw["display_refresh_hz"] = 1000
        with self.assertRaises(mod.ArenaProfileError):
            mod.admit_profile(raw)

    def test_frame_limit_cannot_exceed_refresh(self):
        raw = self.base()
        raw.update(frame_limit_hz=144, display_refresh_hz=120)
        with self.assertRaises(mod.ArenaProfileError):
            mod.admit_profile(raw)

    def test_boolean_as_integer_is_rejected(self):
        raw = self.base()
        raw["frame_limit_hz"] = True
        with self.assertRaises(mod.ArenaProfileError):
            mod.admit_profile(raw)

    def test_unsupported_governor_is_rejected(self):
        raw = self.base()
        raw["cpu_governor"] = "userspace"
        with self.assertRaises(mod.ArenaProfileError):
            mod.admit_profile(raw)

    def test_performance_cannot_disable_ai_yield(self):
        raw = self.base("performance")
        raw["local_ai_yield"] = False
        with self.assertRaises(mod.ArenaProfileError):
            mod.admit_profile(raw)

    def test_quiet_profile_may_override_within_bounds(self):
        raw = self.base("quiet")
        raw.update(frame_limit_hz=45, display_refresh_hz=60)
        admitted = mod.admit_profile(raw)
        self.assertEqual((admitted.frame_limit_hz, admitted.display_refresh_hz), (45, 60))

    def test_schema_drift_is_rejected(self):
        raw = self.base()
        raw["schema_version"] = 2
        with self.assertRaises(mod.ArenaProfileError):
            mod.admit_profile(raw)


if __name__ == "__main__":
    unittest.main()

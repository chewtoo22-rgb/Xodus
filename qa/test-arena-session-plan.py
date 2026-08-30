#!/usr/bin/env python3
import importlib.util
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "xodus-arena-session-plan"
spec = importlib.util.spec_from_file_location("xodus_arena_session_plan", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def preflight(**overrides):
    value = {
        "schema": 1,
        "ready": True,
        "blockers": [],
        "warnings": [],
        "gpu_vendors": ["intel"],
        "require_steam": False,
        "policy": {
            "read_only_preflight": True,
            "state_changes_performed": False,
            "hardware_validation_claim": False,
            "launch_authorized": True,
        },
    }
    value.update(overrides)
    return value


class ArenaSessionPlanTests(unittest.TestCase):
    def test_builds_fixed_gamescope_steam_plan(self):
        plan = mod.build_plan(preflight(), 1920, 1080, 60, True)
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["target"], "steam_gamepadui")
        self.assertEqual(plan["argv"], [
            "/usr/bin/gamescope", "-f", "-W", "1920", "-H", "1080", "-r", "60", "--",
            "/usr/bin/steam", "-gamepadui",
        ])
        self.assertFalse(plan["policy"]["exec_performed"])
        self.assertFalse(plan["policy"]["hardware_validation_claim"])

    def test_default_shell_plan_is_fixed(self):
        plan = mod.build_plan(preflight(), 2560, 1440, 120, False)
        self.assertEqual(plan["target"], "xodus_arena_shell")
        self.assertEqual(plan["argv"][-1], "/usr/bin/xodus-arena-shell")

    def test_rejects_not_ready_or_unauthorized_preflight(self):
        with self.assertRaisesRegex(ValueError, "not ready"):
            mod.build_plan(preflight(ready=False), 1920, 1080, 60, True)
        denied = preflight()
        denied["policy"] = dict(denied["policy"], launch_authorized=False)
        with self.assertRaisesRegex(ValueError, "did not authorize"):
            mod.build_plan(denied, 1920, 1080, 60, True)

    def test_rejects_ready_with_blockers_or_false_claims(self):
        with self.assertRaisesRegex(ValueError, "cannot contain blockers"):
            mod.build_plan(preflight(blockers=["gamescope_unavailable"]), 1920, 1080, 60, True)
        claimed = preflight()
        claimed["policy"] = dict(claimed["policy"], hardware_validation_claim=True)
        with self.assertRaisesRegex(ValueError, "must not claim"):
            mod.build_plan(claimed, 1920, 1080, 60, True)

    def test_rejects_display_bounds(self):
        for width, height, refresh in [(639, 1080, 60), (1920, 9000, 60), (1920, 1080, 241)]:
            with self.assertRaises(ValueError):
                mod.build_plan(preflight(), width, height, refresh, True)

    def test_preflight_can_require_steam(self):
        with self.assertRaisesRegex(ValueError, "requires Steam"):
            mod.build_plan(preflight(require_steam=True), 1920, 1080, 60, False)

    def test_rejects_schema_drift_and_unknown_gpu(self):
        drift = preflight(extra=True)
        with self.assertRaisesRegex(ValueError, "unexpected preflight schema"):
            mod.build_plan(drift, 1920, 1080, 60, True)
        with self.assertRaisesRegex(ValueError, "known GPU"):
            mod.build_plan(preflight(gpu_vendors=["mystery"]), 1920, 1080, 60, True)

    def test_loader_rejects_symlink_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            target = root / "real.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "preflight.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                mod.load_preflight(str(link))


if __name__ == "__main__":
    unittest.main()

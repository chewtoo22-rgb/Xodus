#!/usr/bin/env python3
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "xodus-arena-session-plan"


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


def run(data, *args, symlink=False):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        real = root / "preflight-real.json"
        real.write_text(json.dumps(data), encoding="utf-8")
        path = real
        if symlink:
            path = root / "preflight.json"
            path.symlink_to(real)
        proc = subprocess.run(
            ["python3", str(SCRIPT), "--preflight", str(path), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=5,
        )
        return proc.returncode, json.loads(proc.stdout)


class ArenaSessionPlanTests(unittest.TestCase):
    def test_builds_fixed_gamescope_steam_plan(self):
        code, plan = run(preflight(), "--steam")
        self.assertEqual(code, 0)
        self.assertEqual(plan["target"], "steam_gamepadui")
        self.assertEqual(plan["argv"], [
            "/usr/bin/gamescope", "-f", "-W", "1920", "-H", "1080", "-r", "60", "--",
            "/usr/bin/steam", "-gamepadui",
        ])
        self.assertFalse(plan["policy"]["exec_performed"])
        self.assertFalse(plan["policy"]["hardware_validation_claim"])

    def test_default_shell_plan_is_fixed(self):
        code, plan = run(preflight(), "--width", "2560", "--height", "1440", "--refresh", "120")
        self.assertEqual(code, 0)
        self.assertEqual(plan["target"], "xodus_arena_shell")
        self.assertEqual(plan["argv"][-1], "/usr/bin/xodus-arena-shell")
        self.assertEqual(plan["display"], {"width": 2560, "height": 1440, "refresh_hz": 120})

    def test_rejects_not_ready_or_unauthorized_preflight(self):
        code, result = run(preflight(ready=False), "--steam")
        self.assertEqual(code, 2)
        self.assertIn("not ready", result["error"])
        denied = preflight()
        denied["policy"] = dict(denied["policy"], launch_authorized=False)
        code, result = run(denied, "--steam")
        self.assertEqual(code, 2)
        self.assertIn("did not authorize", result["error"])

    def test_rejects_ready_with_blockers_or_false_claims(self):
        code, result = run(preflight(blockers=["gamescope_unavailable"]), "--steam")
        self.assertEqual(code, 2)
        self.assertIn("cannot contain blockers", result["error"])
        claimed = preflight()
        claimed["policy"] = dict(claimed["policy"], hardware_validation_claim=True)
        code, result = run(claimed, "--steam")
        self.assertEqual(code, 2)
        self.assertIn("must not claim", result["error"])

    def test_rejects_display_bounds(self):
        for args in [
            ("--width", "639"),
            ("--height", "9000"),
            ("--refresh", "241"),
        ]:
            code, result = run(preflight(), "--steam", *args)
            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "blocked")

    def test_preflight_can_require_steam(self):
        code, result = run(preflight(require_steam=True))
        self.assertEqual(code, 2)
        self.assertIn("requires Steam", result["error"])

    def test_rejects_schema_drift_and_unknown_gpu(self):
        code, result = run(preflight(extra=True), "--steam")
        self.assertEqual(code, 2)
        self.assertIn("unexpected preflight schema", result["error"])
        code, result = run(preflight(gpu_vendors=["mystery"]), "--steam")
        self.assertEqual(code, 2)
        self.assertIn("known GPU", result["error"])

    def test_rejects_symlink_evidence(self):
        code, result = run(preflight(), "--steam", symlink=True)
        self.assertEqual(code, 2)
        self.assertIn("non-symlink", result["error"])


if __name__ == "__main__":
    unittest.main()

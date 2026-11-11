from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qa"))

from xodus_studio_contract import ContractError, load, validate  # noqa: E402

_spec = importlib.util.spec_from_file_location("xodus_studio_plan", ROOT / "scripts" / "xodus-studio-plan.py")
plan_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_mod)
PLANNER = ROOT / "scripts" / "xodus-studio-plan.py"


class StudioContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load()

    def mutate(self, fn) -> None:
        data = copy.deepcopy(self.data)
        fn(data)
        with self.assertRaises(ContractError):
            validate(data)

    def test_repository_manifest_is_valid(self) -> None:
        packages = validate(self.data)
        self.assertIn("godot", packages)
        self.assertIn("vulkan-intel", packages)

    def test_rejects_iso_default(self) -> None:
        self.mutate(lambda d: d.__setitem__("iso_default", True))

    def test_rejects_extra_repo(self) -> None:
        self.mutate(lambda d: d.__setitem__("allowed_repos", ["core", "extra", "aur"]))

    def test_rejects_unknown_key(self) -> None:
        self.mutate(lambda d: d.__setitem__("aur_helper", "yay"))

    def test_rejects_cross_profile_duplicate(self) -> None:
        self.mutate(lambda d: d["profiles"]["art"]["packages"].append("godot"))

    def test_rejects_invalid_package_name(self) -> None:
        self.mutate(lambda d: d["profiles"]["art"]["packages"].append("blender; rm -rf /"))

    def test_rejects_option_like_package(self) -> None:
        self.mutate(lambda d: d["profiles"]["art"]["packages"].append("--overwrite=*"))

    def test_rejects_dependency_cycle(self) -> None:
        self.mutate(lambda d: d["profiles"]["toolchain"]["requires"].append("engines"))

    def test_rejects_unknown_requirement(self) -> None:
        self.mutate(lambda d: d["profiles"]["engines"]["requires"].append("ghost"))

    def test_rejects_missing_gpu_vendor(self) -> None:
        self.mutate(lambda d: d["gpu_vulkan_drivers"].pop("nvidia"))

    def test_rejects_empty_gpu_driver(self) -> None:
        self.mutate(lambda d: d["gpu_vulkan_drivers"].__setitem__("amd", []))

    def test_rejects_duplicate_json_key(self) -> None:
        from xodus_studio_contract import reject_duplicate_keys
        with self.assertRaisesRegex(ValueError, "duplicate key: schema"):
            json.loads('{"schema": 1, "schema": 2}', object_pairs_hook=reject_duplicate_keys)


class StudioPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = plan_mod.load_manifest()

    def test_engines_pull_in_graphics_and_toolchain(self) -> None:
        plan = plan_mod.build_plan(self.manifest, ["engines"], ["amd"])
        self.assertEqual(plan["profiles"], ["toolchain", "graphics", "engines"])
        for pkg in ("godot", "vulkan-headers", "cmake", "vulkan-radeon"):
            self.assertIn(pkg, plan["packages"])
        self.assertNotIn("vulkan-intel", plan["packages"])

    def test_plan_is_deterministic_and_non_executing(self) -> None:
        a = plan_mod.build_plan(self.manifest, ["art", "engines"], ["nvidia", "intel"])
        b = plan_mod.build_plan(self.manifest, ["engines", "art"], ["intel", "nvidia"])
        self.assertEqual(a, b)
        self.assertFalse(a["executed"])
        self.assertFalse(a["network_used"])
        self.assertTrue(a["requires_user_confirmation"])
        self.assertEqual(a["argv"][:4], ["pacman", "-S", "--needed", "--"])
        self.assertEqual(a["argv"][4:], sorted(a["packages"]))

    def test_gpu_driver_only_with_graphics(self) -> None:
        plan = plan_mod.build_plan(self.manifest, ["art"], ["intel"])
        self.assertNotIn("vulkan-intel", plan["packages"])

    def test_warns_without_gpu_for_graphics(self) -> None:
        plan = plan_mod.build_plan(self.manifest, ["graphics"], [])
        self.assertTrue(plan["warnings"])

    def test_rejects_unknown_profile_and_gpu(self) -> None:
        with self.assertRaises(ValueError):
            plan_mod.build_plan(self.manifest, ["kernel-dev"], [])
        with self.assertRaises(ValueError):
            plan_mod.build_plan(self.manifest, ["art"], ["voodoo"])
        with self.assertRaises(ValueError):
            plan_mod.build_plan(self.manifest, [], [])

    def test_ai_assist_follows_tier_policy(self) -> None:
        small = plan_mod.build_plan(self.manifest, ["ai-assist"], [], ram_gib=4)
        self.assertEqual(small["profiles"], ["editor", "ai-assist"])
        self.assertFalse(small["ai_assistant"]["enabled"])
        self.assertEqual(small["ai_assistant"]["tier"], "disabled")
        nuc = plan_mod.build_plan(self.manifest, ["ai-assist"], ["intel"], ram_gib=16, cpu_threads=8)
        self.assertTrue(nuc["ai_assistant"]["enabled"])
        self.assertEqual(nuc["ai_assistant"]["tier"], "standard")

    def test_ai_assist_requires_ram(self) -> None:
        with self.assertRaises(ValueError):
            plan_mod.build_plan(self.manifest, ["ai-assist"], [])

    def test_cli_emits_json(self) -> None:
        out = subprocess.run([sys.executable, str(PLANNER), "--profile", "engines", "--gpu-vendor", "intel"],
                             capture_output=True, text=True, check=True)
        self.assertIn("godot", json.loads(out.stdout)["packages"])

    def test_cli_rejects_bad_input(self) -> None:
        out = subprocess.run([sys.executable, str(PLANNER), "--profile", "nope"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)

    def test_planner_never_shells_out(self) -> None:
        source = PLANNER.read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "urllib", "socket", "http.client"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("selector", ROOT / "scripts/xodus-ai-select.py")
selector = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(selector)


class SelectorTests(unittest.TestCase):
    def test_low_memory_disables_local_llm(self):
        self.assertEqual(selector.classify(selector.Hardware(6.9)).tier, "disabled")

    def test_lite_boundary(self):
        rec = selector.classify(selector.Hardware(8, 0, "intel"))
        self.assertEqual((rec.tier, rec.max_model_class), ("lite", "1B-3B"))

    def test_nuc_class_is_standard(self):
        rec = selector.classify(selector.Hardware(32, 0, "intel"))
        self.assertEqual(rec.tier, "standard")
        self.assertEqual(rec.backend, "vulkan")

    def test_discrete_gpu_promotes_performance(self):
        rec = selector.classify(selector.Hardware(32, 8, "nvidia"))
        self.assertEqual(rec.tier, "performance")
        self.assertEqual(rec.backend, "cuda")

    def test_workstation_requires_both_ram_and_vram(self):
        self.assertEqual(selector.classify(selector.Hardware(64, 15.9, "nvidia")).tier, "performance")
        self.assertEqual(selector.classify(selector.Hardware(64, 16, "nvidia")).tier, "workstation")

    def test_unknown_gpu_never_claims_acceleration(self):
        rec = selector.classify(selector.Hardware(32, 12, "mystery"))
        self.assertEqual(rec.backend, "cpu")


if __name__ == "__main__":
    unittest.main()

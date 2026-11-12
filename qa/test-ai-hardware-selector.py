#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import math
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("selector", ROOT / "scripts/xodus-ai-select.py")
selector = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = selector
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

    def test_nan_ram_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "RAM must be"):
            selector.classify(selector.Hardware(math.nan, 0, "intel"))

    def test_infinite_vram_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "VRAM must be"):
            selector.classify(selector.Hardware(32, math.inf, "nvidia"))

    def test_negative_resources_are_rejected(self):
        with self.assertRaises(ValueError):
            selector.classify(selector.Hardware(-1, 0, "intel"))
        with self.assertRaises(ValueError):
            selector.classify(selector.Hardware(32, -1, "nvidia"))

    def test_invalid_cpu_thread_counts_are_rejected(self):
        for value in (0, -1, selector.MAX_CPU_THREADS + 1):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "CPU thread count"):
                    selector.classify(selector.Hardware(32, 0, "intel", value))
        with self.assertRaisesRegex(ValueError, "CPU thread count"):
            selector.classify(selector.Hardware(32, 0, "intel", True))

    def test_control_characters_in_vendor_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "control characters"):
            selector.classify(selector.Hardware(32, 8, "nvidia\nspoof"))

    def test_oversized_vendor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "too long"):
            selector.classify(selector.Hardware(32, 8, "x" * (selector.MAX_VENDOR_LEN + 1)))


if __name__ == "__main__":
    unittest.main()

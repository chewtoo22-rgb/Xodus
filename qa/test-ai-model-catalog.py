#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


selector = load_module("selector", ROOT / "scripts/xodus-ai-select.py")
resolver = load_module("resolver", ROOT / "scripts/xodus-ai-resolve-model.py")
CATALOG = json.loads((ROOT / "config/xodus-ai-model-catalog.json").read_text(encoding="utf-8"))


def selector_payload(hw):
    rec = selector.classify(hw)
    return {
        "hardware": {
            "ram_gib": hw.ram_gib,
            "vram_gib": hw.vram_gib,
            "gpu_vendor": hw.gpu_vendor,
            "cpu_threads": hw.cpu_threads,
        },
        "recommendation": {
            "tier": rec.tier,
            "max_model_class": rec.max_model_class,
            "preferred_quant": rec.preferred_quant,
            "backend": rec.backend,
            "reason": rec.reason,
        },
    }


class ModelCatalogTests(unittest.TestCase):
    def test_catalog_contract_is_valid(self):
        resolver.validate_catalog(CATALOG)

    def test_nuc_class_selects_nemotron_standard(self):
        result = resolver.resolve(selector_payload(selector.Hardware(32, 0, "intel", 16)), CATALOG)
        self.assertEqual(result["tier"], "standard")
        self.assertEqual(result["backend"], "vulkan")
        self.assertEqual(result["model"]["family"], "nemotron-nano")
        self.assertEqual(result["model"]["model_id"], "xodus-nemotron-nano-4b-q4")
        self.assertFalse(result["download_requested"])
        self.assertTrue(result["requires_artifact_verification"])

    def test_low_memory_selects_no_model(self):
        result = resolver.resolve(selector_payload(selector.Hardware(6, 0, "none", 4)), CATALOG)
        self.assertEqual(result["tier"], "disabled")
        self.assertIsNone(result["model"]["model_id"])
        self.assertFalse(result["requires_artifact_verification"])

    def test_discrete_nvidia_keeps_selector_backend(self):
        result = resolver.resolve(selector_payload(selector.Hardware(32, 8, "nvidia", 16)), CATALOG)
        self.assertEqual(result["tier"], "performance")
        self.assertEqual(result["backend"], "cuda")

    def test_catalog_cannot_enable_network_downloads(self):
        bad = json.loads(json.dumps(CATALOG))
        bad["policy"]["network_downloads_allowed"] = True
        with self.assertRaises(ValueError):
            resolver.validate_catalog(bad)

    def test_catalog_selector_mismatch_fails_closed(self):
        payload = selector_payload(selector.Hardware(32, 0, "intel", 16))
        payload["recommendation"]["max_model_class"] = "7B-14B"
        with self.assertRaises(ValueError):
            resolver.resolve(payload, CATALOG)

    def test_unknown_tier_fails_closed(self):
        payload = selector_payload(selector.Hardware(32, 0, "intel", 16))
        payload["recommendation"]["tier"] = "turbo-ultra"
        with self.assertRaises(ValueError):
            resolver.resolve(payload, CATALOG)


if __name__ == "__main__":
    unittest.main()

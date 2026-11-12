#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "config/xodus-ai-model-catalog.json"
RESOLVER_PATH = ROOT / "scripts/xodus-ai-resolve-model.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


selector = load_module("xodus_ai_select_for_catalog", ROOT / "scripts/xodus-ai-select.py")
resolver = load_module("xodus_ai_resolve_model", RESOLVER_PATH)
planner = load_module("xodus_ai_launch_plan_for_catalog", ROOT / "scripts/xodus-ai-launch-plan.py")
verifier = load_module("xodus_ai_verify_artifact_for_catalog", ROOT / "scripts/xodus-ai-verify-artifact.py")
CATALOG = resolver.load_json(CATALOG_PATH)


def selector_payload(hw):
    """Mirror the selector CLI output shape exactly."""
    return {
        "hardware": asdict(hw),
        "recommendation": asdict(selector.classify(hw)),
        "network_used": selector.network_used,
        "hardware_validation_claim": selector.hardware_validation_claim,
    }


NUC = selector.Hardware(32.0, 0.0, "intel", 16)


class LaunchPlannerAgreementTests(unittest.TestCase):
    """The launch planner is the reviewed runtime source of truth."""

    def test_catalog_context_matches_launch_planner(self):
        for tier, ctx in planner.CTX_BY_TIER.items():
            self.assertEqual(CATALOG["tiers"][tier]["context_tokens"], ctx, tier)
        self.assertEqual(set(CATALOG["tiers"]) - set(planner.CTX_BY_TIER), {"disabled"})
        self.assertEqual(CATALOG["tiers"]["disabled"]["context_tokens"], 0)

    def test_resolver_context_table_matches_launch_planner(self):
        enabled = {k: v for k, v in resolver.CTX_BY_TIER.items() if k != "disabled"}
        self.assertEqual(enabled, planner.CTX_BY_TIER)
        self.assertEqual(set(planner.TIERS), set(enabled))

    def test_verifier_size_cap_matches_launch_planner(self):
        self.assertEqual(verifier.MAX_ARTIFACT_BYTES, planner.MAX_MODEL_BYTES)

    def test_resolved_context_matches_launch_planner(self):
        result = resolver.resolve(selector_payload(selector.Hardware(64.0, 16.0, "nvidia", 16)), CATALOG)
        self.assertEqual(result["tier"], "workstation")
        self.assertEqual(result["model"]["context_tokens"], planner.CTX_BY_TIER["workstation"])

    def test_drifted_context_fails_closed(self):
        bad = copy.deepcopy(CATALOG)
        bad["tiers"]["performance"]["context_tokens"] = 8192
        with self.assertRaisesRegex(ValueError, "launch planner"):
            resolver.validate_catalog(bad)


class ModelCatalogTests(unittest.TestCase):
    def test_catalog_contract_is_valid(self):
        resolver.validate_catalog(CATALOG)

    def test_catalog_declares_unreviewed_placeholders(self):
        self.assertEqual(CATALOG["review"]["status"], "unreviewed_placeholder")
        self.assertIs(CATALOG["review"]["entries_reviewed"], False)
        self.assertIs(CATALOG["hardware_validation_claim"], False)
        for tier, entry in CATALOG["tiers"].items():
            self.assertIs(entry["reviewed"], False, tier)
        # No invented download sources or digests: no URLs anywhere, no digest/url fields.
        self.assertNotIn("://", CATALOG_PATH.read_text(encoding="utf-8"))
        for entry in CATALOG["tiers"].values():
            self.assertFalse({"sha256", "url", "download_url"} & set(entry))

    def test_nuc_class_selects_nemotron_standard(self):
        result = resolver.resolve(selector_payload(NUC), CATALOG)
        self.assertEqual(result["tier"], "standard")
        self.assertEqual(result["backend"], "vulkan")
        self.assertEqual(result["model"]["family"], "nemotron-nano")
        self.assertEqual(result["model"]["model_id"], "xodus-nemotron-nano-4b-q4")
        self.assertFalse(result["download_requested"])
        self.assertFalse(result["network_used"])
        self.assertFalse(result["executed"])
        self.assertFalse(result["hardware_validation_claim"])
        self.assertFalse(result["model_reviewed"])
        self.assertTrue(result["requires_artifact_verification"])

    def test_low_memory_selects_no_model(self):
        result = resolver.resolve(selector_payload(selector.Hardware(6.0, 0.0, "none", 4)), CATALOG)
        self.assertEqual(result["tier"], "disabled")
        self.assertIsNone(result["model"]["model_id"])
        self.assertFalse(result["requires_artifact_verification"])

    def test_discrete_nvidia_keeps_selector_backend(self):
        result = resolver.resolve(selector_payload(selector.Hardware(32.0, 8.0, "nvidia", 16)), CATALOG)
        self.assertEqual(result["tier"], "performance")
        self.assertEqual(result["backend"], "cuda")
        self.assertEqual(result["model"]["context_tokens"], 16384)

    def test_catalog_cannot_enable_network_downloads(self):
        bad = copy.deepcopy(CATALOG)
        bad["policy"]["network_downloads_allowed"] = True
        with self.assertRaises(ValueError):
            resolver.validate_catalog(bad)

    def test_catalog_cannot_enable_model_switching(self):
        bad = copy.deepcopy(CATALOG)
        bad["policy"]["automatic_model_switching_after_first_boot"] = True
        with self.assertRaisesRegex(ValueError, "switching"):
            resolver.validate_catalog(bad)

    def test_catalog_cannot_claim_review_or_hardware_validation(self):
        for mutate in (
            lambda c: c["review"].__setitem__("entries_reviewed", True),
            lambda c: c["review"].__setitem__("status", "reviewed"),
            lambda c: c["tiers"]["standard"].__setitem__("reviewed", True),
            lambda c: c.__setitem__("hardware_validation_claim", True),
        ):
            bad = copy.deepcopy(CATALOG)
            mutate(bad)
            with self.assertRaises(ValueError):
                resolver.validate_catalog(bad)

    def test_catalog_selector_mismatch_fails_closed(self):
        payload = selector_payload(NUC)
        payload["recommendation"]["max_model_class"] = "7B-14B"
        with self.assertRaises(ValueError):
            resolver.resolve(payload, CATALOG)

    def test_unknown_tier_fails_closed(self):
        payload = selector_payload(NUC)
        payload["recommendation"]["tier"] = "turbo-ultra"
        with self.assertRaises(ValueError):
            resolver.resolve(payload, CATALOG)


class ExactKeySetTests(unittest.TestCase):
    def assert_key_rules(self, getter, label):
        missing = copy.deepcopy(CATALOG)
        target = getter(missing)
        target.pop(sorted(target)[0])
        with self.assertRaisesRegex(ValueError, "missing keys"):
            resolver.validate_catalog(missing)
        extra = copy.deepcopy(CATALOG)
        getter(extra)["download_url"] = "x"
        with self.assertRaisesRegex(ValueError, "unexpected keys.*download_url"):
            resolver.validate_catalog(extra)

    def test_catalog_top_level_exact_keys(self):
        self.assert_key_rules(lambda c: c, "catalog")

    def test_catalog_review_exact_keys(self):
        self.assert_key_rules(lambda c: c["review"], "review")

    def test_catalog_policy_exact_keys(self):
        self.assert_key_rules(lambda c: c["policy"], "policy")

    def test_catalog_tiers_exact_keys(self):
        self.assert_key_rules(lambda c: c["tiers"], "tiers")

    def test_catalog_entry_exact_keys(self):
        self.assert_key_rules(lambda c: c["tiers"]["lite"], "lite")

    def test_selector_exact_keys(self):
        for path in ((), ("hardware",), ("recommendation",)):
            payload = selector_payload(NUC)
            target = payload
            for part in path:
                target = target[part]
            target["unexpected"] = 1
            with self.assertRaisesRegex(ValueError, "unexpected keys"):
                resolver.resolve(payload, CATALOG)
            payload = selector_payload(NUC)
            target = payload
            for part in path:
                target = target[part]
            target.pop(sorted(target)[0])
            with self.assertRaisesRegex(ValueError, "missing keys"):
                resolver.resolve(payload, CATALOG)


class TypeStrictTests(unittest.TestCase):
    def test_bool_schema_version_rejected(self):
        bad = copy.deepcopy(CATALOG)
        bad["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "schema_version"):
            resolver.validate_catalog(bad)

    def test_bool_or_float_context_rejected(self):
        for value in (True, 4096.0, "4096"):
            bad = copy.deepcopy(CATALOG)
            bad["tiers"]["lite"]["context_tokens"] = value
            with self.assertRaisesRegex(ValueError, "context_tokens"):
                resolver.validate_catalog(bad)

    def test_bool_cpu_threads_rejected(self):
        payload = selector_payload(NUC)
        payload["hardware"]["cpu_threads"] = True
        with self.assertRaisesRegex(ValueError, "cpu_threads"):
            resolver.resolve(payload, CATALOG)

    def test_bool_or_nonfinite_ram_rejected(self):
        for value in (True, float("nan"), float("inf"), -1.0, "32"):
            payload = selector_payload(NUC)
            payload["hardware"]["ram_gib"] = value
            with self.assertRaisesRegex(ValueError, "RAM"):
                resolver.resolve(payload, CATALOG)

    def test_selector_claims_must_be_false(self):
        for key in ("network_used", "hardware_validation_claim"):
            for value in (True, 0, None):
                payload = selector_payload(NUC)
                payload[key] = value
                with self.assertRaises(ValueError):
                    resolver.resolve(payload, CATALOG)

    def test_policy_false_markers_reject_falsy_non_bools(self):
        bad = copy.deepcopy(CATALOG)
        bad["policy"]["network_downloads_allowed"] = 0
        with self.assertRaises(ValueError):
            resolver.validate_catalog(bad)

    def test_invalid_model_id_rejected(self):
        for value in ("", "UPPER", "a" * 97, "../escape", 7):
            bad = copy.deepcopy(CATALOG)
            bad["tiers"]["lite"]["model_id"] = value
            with self.assertRaisesRegex(ValueError, "model_id"):
                resolver.validate_catalog(bad)


class ForgedSelectorTests(unittest.TestCase):
    """Review repros: a recommendation must equal what the selector derives."""

    def forged(self, **rec_overrides):
        hw = selector.Hardware(8.0, 0.0, "intel", 8)
        payload = selector_payload(hw)
        payload["recommendation"].update(rec_overrides)
        return payload

    def test_forged_workstation_tier_on_8gib_rejected(self):
        payload = self.forged(tier="workstation", max_model_class="20B-30B", backend="cuda")
        with self.assertRaisesRegex(ValueError, "does not match hardware policy"):
            resolver.resolve(payload, CATALOG)

    def test_backend_must_match_gpu_vendor(self):
        hw = selector.Hardware(32.0, 0.0, "intel", 16)
        payload = selector_payload(hw)
        payload["recommendation"]["backend"] = "cuda"
        with self.assertRaisesRegex(ValueError, "backend"):
            resolver.resolve(payload, CATALOG)

    def test_control_characters_in_gpu_vendor_rejected(self):
        payload = selector_payload(selector.Hardware(32.0, 0.0, "intel", 16))
        payload["hardware"]["gpu_vendor"] = "intel\x1b[31m"
        with self.assertRaisesRegex(ValueError, "selector policy"):
            resolver.resolve(payload, CATALOG)

    def test_genuine_selector_output_still_resolves(self):
        for hw in (selector.Hardware(8.0, 0.0, "intel", 8), selector.Hardware(64.0, 16.0, "nvidia", 32)):
            with self.subTest(hw=hw):
                result = resolver.resolve(selector_payload(hw), CATALOG)
                self.assertEqual(result["tier"], selector.classify(hw).tier)


class HostileInputTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_huge_integer_ram_rejected_cleanly(self):
        payload = selector_payload(NUC)
        payload["hardware"]["ram_gib"] = 10 ** 400
        with self.assertRaisesRegex(ValueError, "finite"):
            resolver.resolve(payload, CATALOG)

    def test_deeply_nested_json_rejected_cleanly(self):
        path = self.root / "deep.json"
        path.write_text("[" * 100000 + "]" * 100000, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "malformed JSON"):
            resolver.load_json(path)

    def test_oversized_input_rejected(self):
        path = self.root / "big.json"
        path.write_text('{"x": "' + "a" * resolver.MAX_INPUT_BYTES + '"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exceeds"):
            resolver.load_json(path)

    def test_cli_exits_2_on_hostile_input(self):
        path = self.root / "deep.json"
        path.write_text("[" * 100000, encoding="utf-8")
        out = subprocess.run([sys.executable, str(RESOLVER_PATH), "--selector-json", str(path),
                              "--catalog", str(CATALOG_PATH)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2, out.stderr)


class InputFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_duplicate_json_key_rejected(self):
        path = self.root / "catalog.json"
        path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            resolver.load_json(path)

    def test_nested_duplicate_json_key_rejected(self):
        text = CATALOG_PATH.read_text(encoding="utf-8").replace(
            '"selection_basis": "hardware_only",',
            '"selection_basis": "hardware_only", "selection_basis": "hardware_only",', 1)
        path = self.root / "catalog.json"
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            resolver.load_json(path)

    def test_symlink_input_rejected(self):
        link = self.root / "catalog.json"
        link.symlink_to(CATALOG_PATH)
        with self.assertRaisesRegex(ValueError, "symlink"):
            resolver.load_json(link)

    def test_non_regular_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "regular file"):
            resolver.load_json(self.root)

    def test_fifo_input_rejected(self):
        fifo = self.root / "selector.json"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, "regular file"):
            resolver.load_json(fifo)

    def test_missing_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot inspect"):
            resolver.load_json(self.root / "absent.json")

    def test_non_object_top_level_rejected(self):
        path = self.root / "x.json"
        path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "object"):
            resolver.load_json(path)

    def test_cli_round_trip_and_failure(self):
        sel = self.root / "selector.json"
        sel.write_text(json.dumps(selector_payload(NUC)), encoding="utf-8")
        ok = subprocess.run(
            [sys.executable, str(RESOLVER_PATH), "--selector-json", str(sel), "--catalog", str(CATALOG_PATH)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["tier"], "standard")
        sel.write_text('{"hardware": {}, "hardware": {}}', encoding="utf-8")
        bad = subprocess.run(
            [sys.executable, str(RESOLVER_PATH), "--selector-json", str(sel), "--catalog", str(CATALOG_PATH)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(bad.returncode, 2)
        self.assertIn("duplicate JSON key", bad.stderr)


if __name__ == "__main__":
    unittest.main()

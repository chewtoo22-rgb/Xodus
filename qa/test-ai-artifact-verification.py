#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "scripts" / "xodus-ai-verify-artifact.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = load_module("xodus_ai_verify_artifact", VERIFIER_PATH)
selector = load_module("xodus_ai_select_for_verifier", ROOT / "scripts" / "xodus-ai-select.py")
resolver = load_module("xodus_ai_resolve_for_verifier", ROOT / "scripts" / "xodus-ai-resolve-model.py")
CATALOG = resolver.load_json(ROOT / "config" / "xodus-ai-model-catalog.json")


def nuc_selection() -> dict:
    hw = selector.Hardware(32.0, 0.0, "intel", 16)
    payload = {
        "hardware": asdict(hw),
        "recommendation": asdict(selector.classify(hw)),
        "network_used": False,
        "hardware_validation_claim": False,
    }
    return resolver.resolve(payload, CATALOG)


class ArtifactVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_fixture(self, payload: bytes = b"synthetic-gguf-fixture"):
        artifact = self.root / "nemotron-test.Q4_K_M.gguf"
        artifact.write_bytes(payload)
        selection = nuc_selection()
        model_id = selection["model"]["model_id"]
        manifest = {
            "schema_version": 1,
            "network_downloads_allowed": False,
            "artifacts": {
                model_id: {
                    "filename": artifact.name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                    "format": "gguf",
                    "quant": "Q4_K_M",
                }
            },
        }
        return artifact, selection, manifest

    def entry(self, manifest, selection):
        return manifest["artifacts"][selection["model"]["model_id"]]

    # Happy path -------------------------------------------------------------

    def test_verified_artifact_is_install_ready(self):
        artifact, selection, manifest = self.make_fixture()
        result = MOD.verify(selection, manifest, artifact, CATALOG)
        self.assertTrue(result["verified"])
        self.assertTrue(result["artifact_matches_manifest"])
        self.assertNotIn("ready_for_local_install", result)
        self.assertFalse(result["network_used"])
        self.assertFalse(result["executed"])
        self.assertFalse(result["hardware_validation_claim"])
        self.assertFalse(result["model_reviewed"])
        self.assertEqual(result["sha256"], self.entry(manifest, selection)["sha256"])

    def test_resolver_output_keys_match_verifier_contract(self):
        selection = nuc_selection()
        self.assertEqual(set(selection), MOD.SELECTION_KEYS)
        self.assertEqual(set(selection["model"]), MOD.MODEL_KEYS)

    # Artifact integrity -----------------------------------------------------

    def test_tampered_artifact_fails_closed(self):
        artifact, selection, manifest = self.make_fixture()
        artifact.write_bytes(b"tampered-same-size-data!"[: artifact.stat().st_size])
        with self.assertRaisesRegex(ValueError, "sha256"):
            MOD.verify(selection, manifest, artifact, CATALOG)

    def test_digest_comparison_is_constant_time(self):
        artifact, selection, manifest = self.make_fixture()
        with mock.patch.object(MOD.hmac, "compare_digest", wraps=MOD.hmac.compare_digest) as spy:
            MOD.verify(selection, manifest, artifact, CATALOG)
        spy.assert_called_once()

    def test_size_mismatch_fails_before_hashing(self):
        artifact, selection, manifest = self.make_fixture()
        artifact.write_bytes(artifact.read_bytes() + b"x")
        with mock.patch.object(MOD.hashlib, "sha256", side_effect=AssertionError("hashed")):
            with self.assertRaisesRegex(ValueError, "size"):
                MOD.verify(selection, manifest, artifact, CATALOG)

    def test_symlink_artifact_is_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        link = self.root / "link.gguf"
        link.symlink_to(artifact)
        self.entry(manifest, selection)["filename"] = link.name
        with self.assertRaisesRegex(ValueError, "symlink"):
            MOD.verify(selection, manifest, link, CATALOG)

    def test_directory_artifact_is_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        directory = self.root / "dir.gguf"
        directory.mkdir()
        self.entry(manifest, selection)["filename"] = directory.name
        with self.assertRaisesRegex(ValueError, "regular file"):
            MOD.verify(selection, manifest, directory, CATALOG)

    def test_fifo_artifact_is_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        fifo = self.root / "pipe.gguf"
        os.mkfifo(fifo)
        self.entry(manifest, selection)["filename"] = fifo.name
        with self.assertRaisesRegex(ValueError, "regular file"):
            MOD.verify(selection, manifest, fifo, CATALOG)

    def test_missing_artifact_is_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        artifact.unlink()
        with self.assertRaisesRegex(ValueError, "cannot inspect"):
            MOD.verify(selection, manifest, artifact, CATALOG)

    def test_filename_mismatch_is_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        other = self.root / "other.gguf"
        other.write_bytes(artifact.read_bytes())
        with self.assertRaisesRegex(ValueError, "filename"):
            MOD.verify(selection, manifest, other, CATALOG)

    # Manifest contract --------------------------------------------------------

    def test_unknown_model_is_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        manifest["artifacts"] = {"unknown/model": manifest["artifacts"].popitem()[1]}
        with self.assertRaisesRegex(ValueError, "not present"):
            MOD.verify(selection, manifest, artifact, CATALOG)

    def test_quant_mismatch_is_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        self.entry(manifest, selection)["quant"] = "Q8_0"
        with self.assertRaisesRegex(ValueError, "quant"):
            MOD.verify(selection, manifest, artifact, CATALOG)

    def test_network_enabled_manifest_is_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        for value in (True, 0, None):
            manifest["network_downloads_allowed"] = value
            with self.assertRaisesRegex(ValueError, "network downloads"):
                MOD.verify(selection, manifest, artifact, CATALOG)

    def test_manifest_exact_keys(self):
        artifact, selection, manifest = self.make_fixture()
        extra = copy.deepcopy(manifest)
        extra["download_url"] = "x"
        with self.assertRaisesRegex(ValueError, "unexpected keys.*download_url"):
            MOD.verify(selection, extra, artifact, CATALOG)
        missing = copy.deepcopy(manifest)
        del missing["network_downloads_allowed"]
        with self.assertRaisesRegex(ValueError, "missing keys.*network_downloads_allowed"):
            MOD.verify(selection, missing, artifact, CATALOG)

    def test_manifest_artifact_entry_exact_keys(self):
        artifact, selection, manifest = self.make_fixture()
        extra = copy.deepcopy(manifest)
        self.entry(extra, selection)["url"] = "x"
        with self.assertRaisesRegex(ValueError, "unexpected keys.*url"):
            MOD.verify(selection, extra, artifact, CATALOG)
        missing = copy.deepcopy(manifest)
        del self.entry(missing, selection)["format"]
        with self.assertRaisesRegex(ValueError, "missing keys.*format"):
            MOD.verify(selection, missing, artifact, CATALOG)

    def test_bool_schema_version_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        manifest["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "manifest schema_version"):
            MOD.verify(selection, manifest, artifact, CATALOG)
        manifest["schema_version"] = 1
        selection["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "selection schema_version"):
            MOD.verify(selection, manifest, artifact, CATALOG)

    def test_bool_or_float_size_rejected(self):
        artifact, selection, manifest = self.make_fixture(b"x")
        for value in (True, 1.0, "1", 0, -1, MOD.MAX_ARTIFACT_BYTES + 1):
            self.entry(manifest, selection)["size_bytes"] = value
            with self.assertRaisesRegex(ValueError, "size_bytes"):
                MOD.verify(selection, manifest, artifact, CATALOG)

    def test_malformed_sha256_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        good = self.entry(manifest, selection)["sha256"]
        for value in ("0_" + good[2:], "+" + good[1:], good.upper(), good[:-1], good + "0", 7):
            self.entry(manifest, selection)["sha256"] = value
            with self.assertRaisesRegex(ValueError, "invalid sha256"):
                MOD.verify(selection, manifest, artifact, CATALOG)

    def test_non_basename_filename_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        for value in ("../x.gguf", "sub/x.gguf", "", ".."):
            self.entry(manifest, selection)["filename"] = value
            with self.assertRaisesRegex(ValueError, "basename"):
                MOD.verify(selection, manifest, artifact, CATALOG)

    def test_non_gguf_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        self.entry(manifest, selection)["filename"] = "model.bin"
        with self.assertRaisesRegex(ValueError, "GGUF"):
            MOD.verify(selection, manifest, artifact, CATALOG)
        self.entry(manifest, selection)["filename"] = artifact.name
        self.entry(manifest, selection)["format"] = "safetensors"
        with self.assertRaisesRegex(ValueError, "format"):
            MOD.verify(selection, manifest, artifact, CATALOG)

    # Selection contract ------------------------------------------------------

    def test_selection_exact_keys(self):
        artifact, selection, manifest = self.make_fixture()
        extra = copy.deepcopy(selection)
        extra["surprise"] = 1
        with self.assertRaisesRegex(ValueError, "unexpected keys.*surprise"):
            MOD.verify(extra, manifest, artifact, CATALOG)
        missing = copy.deepcopy(selection)
        del missing["download_requested"]
        with self.assertRaisesRegex(ValueError, "missing keys.*download_requested"):
            MOD.verify(missing, manifest, artifact, CATALOG)

    def test_selection_model_exact_keys(self):
        artifact, selection, manifest = self.make_fixture()
        extra = copy.deepcopy(selection)
        extra["model"]["url"] = "x"
        with self.assertRaisesRegex(ValueError, "unexpected keys.*url"):
            MOD.verify(extra, manifest, artifact, CATALOG)
        missing = copy.deepcopy(selection)
        del missing["model"]["quant"]
        with self.assertRaisesRegex(ValueError, "missing keys.*quant"):
            MOD.verify(missing, manifest, artifact, CATALOG)

    def test_selection_must_not_request_download(self):
        artifact, selection, manifest = self.make_fixture()
        selection["download_requested"] = 0
        with self.assertRaisesRegex(ValueError, "download"):
            MOD.verify(selection, manifest, artifact, CATALOG)

    def test_disabled_selection_is_rejected(self):
        artifact, selection, manifest = self.make_fixture()
        selection["requires_artifact_verification"] = 1
        with self.assertRaisesRegex(ValueError, "does not require"):
            MOD.verify(selection, manifest, artifact, CATALOG)

    def test_selection_claims_must_be_false(self):
        for key in ("network_used", "executed", "hardware_validation_claim", "model_reviewed"):
            artifact, selection, manifest = self.make_fixture()
            selection[key] = True
            with self.assertRaisesRegex(ValueError, key):
                MOD.verify(selection, manifest, artifact, CATALOG)

    # Input files ---------------------------------------------------------------

    def test_junk_selection_fields_rejected(self):
        """Review repro: the verifier certified tier 'turbo' / backend 'none' / reviewed model."""
        mutations = {
            "tier": lambda s: s.__setitem__("tier", "turbo"),
            "backend": lambda s: s.__setitem__("backend", "none"),
            "hardware": lambda s: s.__setitem__("hardware", "lol"),
            "model.reviewed": lambda s: s["model"].__setitem__("reviewed", True),
            "model.engine": lambda s: s["model"].__setitem__("engine", "evil"),
            "model.context": lambda s: s["model"].__setitem__("context_tokens", 10 ** 9),
        }
        for name, mutate in mutations.items():
            with self.subTest(field=name):
                artifact, selection, manifest = self.make_fixture()
                mutate(selection)
                with self.assertRaises(ValueError):
                    MOD.verify(selection, manifest, artifact, CATALOG)

    def test_forged_tier_selection_rejected(self):
        """A selection claiming workstation on 8 GiB/Intel is refused before hashing."""
        artifact, selection, manifest = self.make_fixture()
        selection["hardware"] = {"ram_gib": 8.0, "vram_gib": 0.0, "gpu_vendor": "intel", "cpu_threads": 8}
        with mock.patch.object(MOD, "_hash_regular_file", side_effect=AssertionError("hashed")):
            with self.assertRaisesRegex(ValueError, "hardware policy and catalog"):
                MOD.verify(selection, manifest, artifact, CATALOG)

    def test_duplicate_json_key_rejected(self):
        path = self.root / "manifest.json"
        path.write_text('{"schema_version": 1, "artifacts": {"a": {"x": 1, "x": 2}}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            MOD.load_object(path)

    def test_symlink_json_input_rejected(self):
        target = self.root / "real.json"
        target.write_text("{}", encoding="utf-8")
        link = self.root / "manifest.json"
        link.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            MOD.load_object(link)

    def test_non_regular_json_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "regular file"):
            MOD.load_object(self.root)
        fifo = self.root / "selection.json"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, "regular file"):
            MOD.load_object(fifo)

    def test_cli_contract(self):
        artifact, selection, manifest = self.make_fixture()
        sel = self.root / "selection.json"
        man = self.root / "manifest.json"
        sel.write_text(json.dumps(selection), encoding="utf-8")
        man.write_text(json.dumps(manifest), encoding="utf-8")
        argv = [sys.executable, str(VERIFIER_PATH), "--selection-json", str(sel),
                "--manifest", str(man), "--artifact", str(artifact)]
        ok = subprocess.run(argv, capture_output=True, text=True, check=False)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["verified"])
        artifact.write_bytes(b"X" * len(b"synthetic-gguf-fixture"))
        bad = subprocess.run(argv, capture_output=True, text=True, check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("artifact sha256 does not match manifest", bad.stderr)
        self.assertEqual(bad.stdout, "")


if __name__ == "__main__":
    unittest.main()

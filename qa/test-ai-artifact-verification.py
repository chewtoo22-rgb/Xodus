#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "xodus_ai_verify_artifact", ROOT / "scripts" / "xodus-ai-verify-artifact.py"
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ArtifactVerificationTests(unittest.TestCase):
    def make_fixture(self, root: Path, payload: bytes = b"synthetic-gguf-fixture"):
        artifact = root / "nemotron-test.Q4_K_M.gguf"
        artifact.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        model_id = "nvidia/nemotron-test"
        selection = {
            "schema_version": 1,
            "download_requested": False,
            "requires_artifact_verification": True,
            "model": {"model_id": model_id, "quant": "Q4_K_M"},
        }
        manifest = {
            "schema_version": 1,
            "network_downloads_allowed": False,
            "artifacts": {
                model_id: {
                    "filename": artifact.name,
                    "sha256": digest,
                    "size_bytes": len(payload),
                    "format": "gguf",
                    "quant": "Q4_K_M",
                }
            },
        }
        return artifact, selection, manifest

    def test_verified_artifact_is_install_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact, selection, manifest = self.make_fixture(Path(tmp))
            result = MOD.verify(selection, manifest, artifact)
            self.assertTrue(result["verified"])
            self.assertTrue(result["ready_for_local_install"])
            self.assertFalse(result["network_used"])
            self.assertEqual(result["sha256"], manifest["artifacts"][result["model_id"]]["sha256"])

    def test_tampered_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact, selection, manifest = self.make_fixture(Path(tmp))
            artifact.write_bytes(b"tampered-same-size-data!"[: artifact.stat().st_size])
            with self.assertRaisesRegex(ValueError, "sha256"):
                MOD.verify(selection, manifest, artifact)

    def test_size_mismatch_fails_before_hash_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact, selection, manifest = self.make_fixture(Path(tmp))
            artifact.write_bytes(artifact.read_bytes() + b"x")
            with self.assertRaisesRegex(ValueError, "size"):
                MOD.verify(selection, manifest, artifact)

    def test_symlink_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact, selection, manifest = self.make_fixture(root)
            link = root / "link.gguf"
            link.symlink_to(artifact)
            manifest["artifacts"][selection["model"]["model_id"]]["filename"] = link.name
            with self.assertRaisesRegex(ValueError, "symlink"):
                MOD.verify(selection, manifest, link)

    def test_unreviewed_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact, selection, manifest = self.make_fixture(Path(tmp))
            selection["model"]["model_id"] = "unknown/model"
            with self.assertRaisesRegex(ValueError, "reviewed manifest"):
                MOD.verify(selection, manifest, artifact)

    def test_quant_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact, selection, manifest = self.make_fixture(Path(tmp))
            manifest["artifacts"][selection["model"]["model_id"]]["quant"] = "Q8_0"
            with self.assertRaisesRegex(ValueError, "quant"):
                MOD.verify(selection, manifest, artifact)

    def test_network_enabled_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact, selection, manifest = self.make_fixture(Path(tmp))
            manifest["network_downloads_allowed"] = True
            with self.assertRaisesRegex(ValueError, "network downloads"):
                MOD.verify(selection, manifest, artifact)

    def test_cli_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact, selection, manifest = self.make_fixture(root)
            (root / "selection.json").write_text(json.dumps(selection), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(artifact.exists())


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Verify a locally supplied Xodus model artifact against a supplied manifest.

This boundary is intentionally offline and fail-closed. It never downloads models,
follows symlinks, or mutates the supplied artifact. The manifest is an input to
this check, not a review record: a successful verification proves the local file
matches the manifest's filename, size and sha256, nothing more.

MAX_ARTIFACT_BYTES mirrors MAX_MODEL_BYTES in scripts/xodus-ai-launch-plan.py;
qa/test-ai-model-catalog.py fails when the two drift.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

SUPPORTED_SCHEMA = 1
# Explicit contract markers consumed by the offline-boundary QA gate.
network_used = False
hardware_validation_claim = False

# Must equal MAX_MODEL_BYTES in scripts/xodus-ai-launch-plan.py (cross-checked in QA).
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024 * 1024
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,95}$")
QUANT = re.compile(r"^[A-Za-z0-9_]{1,32}$")

MANIFEST_KEYS = {"schema_version", "network_downloads_allowed", "artifacts"}
ARTIFACT_KEYS = {"filename", "sha256", "size_bytes", "format", "quant"}
# Exactly the output of scripts/xodus-ai-resolve-model.py.
SELECTION_KEYS = {
    "schema_version", "selection_basis", "hardware", "tier", "backend", "model",
    "model_reviewed", "download_requested", "requires_artifact_verification",
    "network_used", "executed", "hardware_validation_claim",
}
MODEL_KEYS = {"model_id", "family", "parameter_class", "quant", "context_tokens", "engine", "reviewed"}
MAX_INPUT_BYTES = 1024 * 1024
RESOLVER_SCRIPT = Path(__file__).resolve().with_name("xodus-ai-resolve-model.py")
DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "config" / "xodus-ai-model-catalog.json"


def load_resolver_module():
    """Load the model resolver, which re-derives a selection from hardware + catalog."""
    spec = importlib.util.spec_from_file_location("xodus_ai_resolve_model", RESOLVER_SCRIPT)
    if spec is None or spec.loader is None:
        raise ValueError("model resolver is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("xodus_ai_resolve_model", module)
    spec.loader.exec_module(module)
    return module


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _require_keys(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: must be an object")
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    if missing or unexpected:
        raise ValueError(f"{where}: missing keys {missing}, unexpected keys {unexpected}")
    return value


def load_object(path: Path) -> dict[str, Any]:
    """Same bounded, non-following, regular-file JSON loader as the resolver."""
    return load_resolver_module().load_json(path)


def validate_manifest(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _require_keys(manifest, MANIFEST_KEYS, "manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != SUPPORTED_SCHEMA:
        raise ValueError("unsupported manifest schema_version")
    if manifest["network_downloads_allowed"] is not False:
        raise ValueError("artifact manifest must keep network downloads disabled")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("manifest must define artifacts")

    for model_id, entry in artifacts.items():
        if not MODEL_ID.fullmatch(model_id):
            raise ValueError("manifest contains invalid model_id")
        _require_keys(entry, ARTIFACT_KEYS, f"manifest artifact {model_id}")
        filename = entry["filename"]
        if (not isinstance(filename, str) or not filename or len(filename) > 255
                or Path(filename).name != filename or filename in {".", ".."}):
            raise ValueError(f"{model_id}: filename must be a basename")
        if not filename.lower().endswith(".gguf"):
            raise ValueError(f"{model_id}: only GGUF artifacts are supported")
        digest = entry["sha256"]
        if not isinstance(digest, str) or not SHA256_HEX.fullmatch(digest):
            raise ValueError(f"{model_id}: invalid sha256 (expected 64 lowercase hex characters)")
        size = entry["size_bytes"]
        if type(size) is not int or size <= 0 or size > MAX_ARTIFACT_BYTES:
            raise ValueError(f"{model_id}: invalid size_bytes")
        if entry["format"] != "gguf":
            raise ValueError(f"{model_id}: unsupported artifact format")
        quant = entry["quant"]
        if not isinstance(quant, str) or not QUANT.fullmatch(quant):
            raise ValueError(f"{model_id}: invalid quant")
    return artifacts


def validate_selection(selection: dict[str, Any]) -> dict[str, Any]:
    _require_keys(selection, SELECTION_KEYS, "selection")
    if type(selection["schema_version"]) is not int or selection["schema_version"] != SUPPORTED_SCHEMA:
        raise ValueError("unsupported selection schema_version")
    if selection["selection_basis"] != "hardware_only":
        raise ValueError("selection must be hardware_only")
    if selection["download_requested"] is not False:
        raise ValueError("selection must not request a download")
    if selection["requires_artifact_verification"] is not True:
        raise ValueError("selection does not require an artifact")
    for key in ("network_used", "executed", "hardware_validation_claim", "model_reviewed"):
        if selection[key] is not False:
            raise ValueError(f"selection {key} must be false")
    return _require_keys(selection["model"], MODEL_KEYS, "selection model")


def _hash_regular_file(artifact: Path, expected_size: int) -> tuple[int, str]:
    """Open without following symlinks, then size-check and hash the same open file."""
    try:
        info = artifact.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect artifact: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ValueError("artifact symlinks are not allowed")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("artifact must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(artifact, flags)
    except OSError as exc:
        raise ValueError(f"cannot open artifact: {exc}") from exc
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("artifact changed during verification")
        # Size is checked before hashing so a wrong file is never hash-accepted.
        if opened.st_size != expected_size:
            raise ValueError("artifact size does not match manifest")
        digest = hashlib.sha256()
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return opened.st_size, digest.hexdigest()


def verify(selection: dict[str, Any], manifest: dict[str, Any], artifact: Path,
           catalog: dict[str, Any]) -> dict[str, Any]:
    artifacts = validate_manifest(manifest)
    model = validate_selection(selection)
    # The selection must be exactly what the resolver derives from its own
    # hardware block and the catalog: a hand-edited tier, backend or model
    # entry is refused before any artifact is opened.
    resolver = load_resolver_module()
    hardware = selection["hardware"]
    _require_keys(hardware, resolver.HARDWARE_KEYS, "selection hardware")
    rebuilt = resolver.resolve({
        "hardware": hardware,
        "recommendation": resolver.expected_recommendation(hardware),
        "network_used": False,
        "hardware_validation_claim": False,
    }, catalog)
    if selection != rebuilt:
        differing = sorted(k for k in rebuilt if selection.get(k) != rebuilt[k])
        raise ValueError(f"selection does not match hardware policy and catalog: {differing}")
    model_id = model["model_id"]
    if not isinstance(model_id, str) or model_id not in artifacts:
        raise ValueError("selected model is not present in supplied manifest")
    expected = artifacts[model_id]
    if expected["quant"] != model["quant"]:
        raise ValueError("manifest quant disagrees with selected model")
    if artifact.name != expected["filename"]:
        raise ValueError("artifact filename does not match manifest")

    size, actual_sha256 = _hash_regular_file(artifact, expected["size_bytes"])
    # Constant-time comparison; both sides are lowercase hex by construction.
    if not hmac.compare_digest(actual_sha256, expected["sha256"]):
        raise ValueError("artifact sha256 does not match manifest")

    return {
        "schema_version": SUPPORTED_SCHEMA,
        "model_id": model_id,
        "artifact": artifact.name,
        "size_bytes": size,
        "sha256": actual_sha256,
        "verified": True,
        "network_used": network_used,
        "executed": False,
        "hardware_validation_claim": hardware_validation_claim,
        "tier": selection["tier"],
        "backend": selection["backend"],
        "model_reviewed": False,
        # Proves only that the file matches the manifest; the catalog entry is
        # still an unreviewed placeholder, so this is not an install approval.
        "artifact_matches_manifest": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-json", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()
    try:
        result = verify(load_object(args.selection_json), load_object(args.manifest), args.artifact,
                        load_object(args.catalog))
    except (OSError, ValueError) as exc:
        print(f"xodus-ai-verify-artifact: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

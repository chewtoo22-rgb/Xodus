#!/usr/bin/env python3
"""Verify a locally supplied Xodus model artifact against a reviewed manifest.

This boundary is intentionally offline and fail-closed. It never downloads models,
follows symlinks, or mutates the supplied artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

SUPPORTED_SCHEMA = 1
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024 * 1024


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be an object")
    return value


def validate_manifest(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if manifest.get("schema_version") != SUPPORTED_SCHEMA:
        raise ValueError("unsupported manifest schema_version")
    if manifest.get("network_downloads_allowed") is not False:
        raise ValueError("artifact manifest must keep network downloads disabled")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("manifest must define artifacts")

    for model_id, entry in artifacts.items():
        if not isinstance(model_id, str) or not model_id or len(model_id) > 96:
            raise ValueError("manifest contains invalid model_id")
        if not isinstance(entry, dict):
            raise ValueError(f"{model_id}: artifact entry must be an object")
        filename = entry.get("filename")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise ValueError(f"{model_id}: filename must be a basename")
        if not filename.lower().endswith(".gguf"):
            raise ValueError(f"{model_id}: only GGUF artifacts are supported")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"{model_id}: invalid sha256")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ValueError(f"{model_id}: invalid sha256") from exc
        size = entry.get("size_bytes")
        if not isinstance(size, int) or size <= 0 or size > MAX_ARTIFACT_BYTES:
            raise ValueError(f"{model_id}: invalid size_bytes")
        if entry.get("format") != "gguf":
            raise ValueError(f"{model_id}: unsupported artifact format")
        quant = entry.get("quant")
        if not isinstance(quant, str) or not quant or len(quant) > 32:
            raise ValueError(f"{model_id}: invalid quant")
    return artifacts


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify(selection: dict[str, Any], manifest: dict[str, Any], artifact: Path) -> dict[str, Any]:
    artifacts = validate_manifest(manifest)
    if selection.get("schema_version") != SUPPORTED_SCHEMA:
        raise ValueError("unsupported selection schema_version")
    if selection.get("download_requested") is not False:
        raise ValueError("selection must not request a download")
    if selection.get("requires_artifact_verification") is not True:
        raise ValueError("selection does not require an artifact")

    model = selection.get("model")
    if not isinstance(model, dict):
        raise ValueError("selection missing model object")
    model_id = model.get("model_id")
    quant = model.get("quant")
    if not isinstance(model_id, str) or model_id not in artifacts:
        raise ValueError("selected model is not present in reviewed manifest")
    expected = artifacts[model_id]
    if expected.get("quant") != quant:
        raise ValueError("manifest quant disagrees with selected model")

    try:
        info = artifact.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect artifact: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ValueError("artifact symlinks are not allowed")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("artifact must be a regular file")
    if artifact.name != expected["filename"]:
        raise ValueError("artifact filename does not match reviewed manifest")
    if info.st_size != expected["size_bytes"]:
        raise ValueError("artifact size does not match reviewed manifest")

    actual_sha256 = sha256_file(artifact)
    if not hashlib.compare_digest(actual_sha256.lower(), expected["sha256"].lower()):
        raise ValueError("artifact sha256 does not match reviewed manifest")

    return {
        "schema_version": SUPPORTED_SCHEMA,
        "model_id": model_id,
        "artifact": artifact.name,
        "size_bytes": info.st_size,
        "sha256": actual_sha256,
        "verified": True,
        "network_used": False,
        "ready_for_local_install": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-json", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(load_object(args.selection_json), load_object(args.manifest), args.artifact)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"xodus-ai-verify-artifact: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

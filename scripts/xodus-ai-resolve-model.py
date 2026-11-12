#!/usr/bin/env python3
"""Resolve a hardware-selector result to one Xodus local-model catalog entry.

This step is intentionally offline and non-executing. It chooses policy, not a
remote download source. Artifact installation/verification remains a separate
release gate (scripts/xodus-ai-verify-artifact.py).

The catalog entries are unreviewed placeholders: every entry must carry
``reviewed: false`` and the catalog must say so in its ``review`` block. The
resolver refuses a catalog that claims review, because no review evidence
mechanism exists yet.

Per-tier context sizes mirror ``CTX_BY_TIER`` in scripts/xodus-ai-launch-plan.py,
which is the reviewed runtime source of truth. qa/test-ai-model-catalog.py fails
when the two drift.
"""
from __future__ import annotations

import argparse
import errno
import importlib.util
import json
import math
import os
import re
import stat
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

SUPPORTED_SCHEMA = 1
# Explicit contract markers consumed by the offline-boundary QA gate.
network_used = False
hardware_validation_claim = False

VALID_TIERS = {"disabled", "lite", "standard", "performance", "workstation"}
VALID_BACKENDS = {"none", "cpu", "cuda", "vulkan"}
# Must equal CTX_BY_TIER in scripts/xodus-ai-launch-plan.py (cross-checked in QA).
CTX_BY_TIER = {
    "disabled": 0,
    "lite": 4096,
    "standard": 8192,
    "performance": 16384,
    "workstation": 32768,
}
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,95}$")
MAX_INPUT_BYTES = 1024 * 1024
MAX_GIB = float(1 << 20)
SELECTOR_SCRIPT = Path(__file__).resolve().with_name("xodus-ai-select.py")

CATALOG_KEYS = {"schema_version", "review", "hardware_validation_claim", "policy", "tiers"}
REVIEW_KEYS = {"status", "entries_reviewed", "note"}
POLICY_KEYS = {"selection_basis", "network_downloads_allowed", "automatic_model_switching_after_first_boot"}
ENTRY_KEYS = {"model_id", "family", "parameter_class", "quant", "context_tokens", "engine", "reviewed"}
SELECTOR_KEYS = {"hardware", "recommendation", "network_used", "hardware_validation_claim"}
HARDWARE_KEYS = {"ram_gib", "vram_gib", "gpu_vendor", "cpu_threads"}
RECOMMENDATION_KEYS = {"tier", "max_model_class", "preferred_quant", "backend", "reason"}


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


def load_json(path: Path) -> dict[str, Any]:
    """Read a bounded regular file without following a symlink, then parse it."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(f"{path}: input symlinks are not allowed") from exc
        raise ValueError(f"{path}: cannot inspect input: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{path}: input must be a regular file")
        if info.st_size > MAX_INPUT_BYTES:
            raise ValueError(f"{path}: input exceeds {MAX_INPUT_BYTES} bytes")
        chunks: list[bytes] = []
        total = 0
        while total <= MAX_INPUT_BYTES:
            chunk = os.read(fd, MAX_INPUT_BYTES + 1 - total)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError(f"{path}: input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise ValueError(f"{path}: malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be an object")
    return value


def _is_int(value: Any) -> bool:
    return type(value) is int


def _is_gib(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and 0 <= value <= MAX_GIB
    except OverflowError:
        return False


def load_selector_module():
    """Load the reviewed hardware selector, the single source of tier policy."""
    spec = importlib.util.spec_from_file_location("xodus_ai_select", SELECTOR_SCRIPT)
    if spec is None or spec.loader is None:
        raise ValueError("hardware selector is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("xodus_ai_select", module)
    spec.loader.exec_module(module)
    return module


def expected_recommendation(hardware: dict[str, Any]) -> dict[str, Any]:
    """Re-derive the recommendation from hardware with the reviewed selector."""
    selector = load_selector_module()
    try:
        rec = selector.classify(selector.Hardware(**hardware))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"selector hardware rejected by selector policy: {exc}") from exc
    return asdict(rec)


def validate_catalog(catalog: dict[str, Any]) -> None:
    _require_keys(catalog, CATALOG_KEYS, "catalog")
    if not _is_int(catalog["schema_version"]) or catalog["schema_version"] != SUPPORTED_SCHEMA:
        raise ValueError("unsupported catalog schema_version")
    if catalog["hardware_validation_claim"] is not False:
        raise ValueError("catalog must not claim hardware validation")

    review = _require_keys(catalog["review"], REVIEW_KEYS, "catalog review")
    if review["status"] != "unreviewed_placeholder" or review["entries_reviewed"] is not False:
        raise ValueError("catalog entries are unreviewed placeholders and must say so")
    if not isinstance(review["note"], str) or not review["note"].strip():
        raise ValueError("catalog review note is required")

    policy = _require_keys(catalog["policy"], POLICY_KEYS, "catalog policy")
    if policy["selection_basis"] != "hardware_only":
        raise ValueError("catalog must enforce hardware_only selection")
    if policy["network_downloads_allowed"] is not False:
        raise ValueError("first-boot resolver must not enable network downloads")
    if policy["automatic_model_switching_after_first_boot"] is not False:
        raise ValueError("catalog must not enable automatic model switching")

    tiers = catalog["tiers"]
    _require_keys(tiers, VALID_TIERS, "catalog tiers")
    for tier, entry in tiers.items():
        _require_keys(entry, ENTRY_KEYS, f"tier {tier}")
        if entry["reviewed"] is not False:
            raise ValueError(f"tier {tier}: placeholder entry cannot claim review")
        context = entry["context_tokens"]
        if not _is_int(context) or context != CTX_BY_TIER[tier]:
            raise ValueError(f"tier {tier}: context_tokens must match launch planner")
        if tier == "disabled":
            if (entry["model_id"] is not None or entry["family"] is not None
                    or entry["engine"] != "none" or entry["quant"] != "none"
                    or entry["parameter_class"] != "none"):
                raise ValueError("disabled tier cannot select a model")
            continue
        model_id = entry["model_id"]
        if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id):
            raise ValueError(f"tier {tier}: invalid model_id")
        family = entry["family"]
        if not isinstance(family, str) or not family or len(family) > 64:
            raise ValueError(f"tier {tier}: invalid family")
        if not isinstance(entry["parameter_class"], str) or not entry["parameter_class"]:
            raise ValueError(f"tier {tier}: invalid parameter_class")
        if entry["quant"] != "Q4_K_M":
            raise ValueError(f"tier {tier}: catalog quant must match selector contract")
        if entry["engine"] != "llama.cpp":
            raise ValueError(f"tier {tier}: unsupported engine")


def validate_selector(selector: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    _require_keys(selector, SELECTOR_KEYS, "selector result")
    if selector["network_used"] is not False:
        raise ValueError("selector result must be offline")
    if selector["hardware_validation_claim"] is not False:
        raise ValueError("selector result must not claim hardware validation")
    hardware = _require_keys(selector["hardware"], HARDWARE_KEYS, "selector hardware")
    rec = _require_keys(selector["recommendation"], RECOMMENDATION_KEYS, "selector recommendation")
    if not _is_gib(hardware["ram_gib"]) or not _is_gib(hardware["vram_gib"]):
        raise ValueError("selector hardware RAM/VRAM must be finite non-negative numbers")
    if not isinstance(hardware["gpu_vendor"], str) or len(hardware["gpu_vendor"]) > 64:
        raise ValueError("selector hardware gpu_vendor is invalid")
    if not _is_int(hardware["cpu_threads"]) or not 1 <= hardware["cpu_threads"] <= 4096:
        raise ValueError("selector hardware cpu_threads is invalid")
    for key in RECOMMENDATION_KEYS:
        if not isinstance(rec[key], str):
            raise ValueError(f"selector recommendation {key} must be a string")
    return hardware, rec


def resolve(selector: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    validate_catalog(catalog)
    hardware, rec = validate_selector(selector)

    # Never trust a recommendation on its word: it must be exactly what the
    # reviewed selector derives from the same hardware.
    expected = expected_recommendation(hardware)
    for key in ("tier", "max_model_class", "preferred_quant", "backend"):
        if rec[key] != expected[key]:
            raise ValueError(f"selector recommendation {key} {rec[key]!r} does not match "
                             f"hardware policy {expected[key]!r}")

    tier = rec["tier"]
    backend = rec["backend"]
    if tier not in VALID_TIERS:
        raise ValueError("selector returned unknown tier")
    if backend not in VALID_BACKENDS:
        raise ValueError("selector returned unknown backend")

    entry = catalog["tiers"][tier]
    if entry["parameter_class"] != rec["max_model_class"]:
        raise ValueError("catalog parameter_class disagrees with selector contract")
    if entry["quant"] != rec["preferred_quant"]:
        raise ValueError("catalog quant disagrees with selector contract")
    if tier == "disabled" and backend != "none":
        raise ValueError("disabled tier must use none backend")
    if tier != "disabled" and backend == "none":
        raise ValueError("enabled tier requires an inference backend")

    return {
        "schema_version": SUPPORTED_SCHEMA,
        "selection_basis": "hardware_only",
        "hardware": dict(hardware),
        "tier": tier,
        "backend": backend,
        "model": dict(entry),
        "model_reviewed": False,
        "download_requested": False,
        "requires_artifact_verification": tier != "disabled",
        "network_used": network_used,
        "executed": False,
        "hardware_validation_claim": hardware_validation_claim,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selector-json", required=True, type=Path)
    parser.add_argument("--catalog", type=Path, default=Path("config/xodus-ai-model-catalog.json"))
    args = parser.parse_args()
    try:
        result = resolve(load_json(args.selector_json), load_json(args.catalog))
    except (OSError, ValueError) as exc:
        print(f"xodus-ai-resolve-model: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

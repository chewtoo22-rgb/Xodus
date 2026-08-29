#!/usr/bin/env python3
"""Resolve a hardware-selector result to one reviewed Xodus local-model entry.

This step is intentionally offline. It chooses policy, not a remote download URL.
Artifact installation/verification remains a separate release gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SUPPORTED_SCHEMA = 1
VALID_TIERS = {"disabled", "lite", "standard", "performance", "workstation"}
VALID_BACKENDS = {"none", "cpu", "cuda", "vulkan"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be an object")
    return value


def validate_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("schema_version") != SUPPORTED_SCHEMA:
        raise ValueError("unsupported catalog schema_version")
    policy = catalog.get("policy")
    if not isinstance(policy, dict) or policy.get("selection_basis") != "hardware_only":
        raise ValueError("catalog must enforce hardware_only selection")
    if policy.get("network_downloads_allowed") is not False:
        raise ValueError("first-boot resolver must not enable network downloads")
    tiers = catalog.get("tiers")
    if not isinstance(tiers, dict) or set(tiers) != VALID_TIERS:
        raise ValueError("catalog must define exactly the supported tiers")
    for tier, entry in tiers.items():
        if not isinstance(entry, dict):
            raise ValueError(f"tier {tier}: entry must be an object")
        if tier == "disabled":
            if entry.get("model_id") is not None or entry.get("engine") != "none":
                raise ValueError("disabled tier cannot select a model")
            continue
        model_id = entry.get("model_id")
        if not isinstance(model_id, str) or not model_id or len(model_id) > 96:
            raise ValueError(f"tier {tier}: invalid model_id")
        if entry.get("quant") != "Q4_K_M":
            raise ValueError(f"tier {tier}: catalog quant must match selector contract")
        if entry.get("engine") != "llama.cpp":
            raise ValueError(f"tier {tier}: unsupported engine")
        context = entry.get("context_tokens")
        if not isinstance(context, int) or context < 2048 or context > 32768:
            raise ValueError(f"tier {tier}: invalid context_tokens")


def resolve(selector: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    validate_catalog(catalog)
    rec = selector.get("recommendation")
    hardware = selector.get("hardware")
    if not isinstance(rec, dict) or not isinstance(hardware, dict):
        raise ValueError("selector result missing hardware/recommendation objects")

    tier = rec.get("tier")
    backend = rec.get("backend")
    if tier not in VALID_TIERS:
        raise ValueError("selector returned unknown tier")
    if backend not in VALID_BACKENDS:
        raise ValueError("selector returned unknown backend")

    entry = catalog["tiers"][tier]
    if entry.get("parameter_class") != rec.get("max_model_class"):
        raise ValueError("catalog parameter_class disagrees with selector contract")
    if entry.get("quant") != rec.get("preferred_quant"):
        raise ValueError("catalog quant disagrees with selector contract")
    if tier == "disabled" and backend != "none":
        raise ValueError("disabled tier must use none backend")
    if tier != "disabled" and backend == "none":
        raise ValueError("enabled tier requires an inference backend")

    return {
        "schema_version": SUPPORTED_SCHEMA,
        "selection_basis": "hardware_only",
        "hardware": hardware,
        "tier": tier,
        "backend": backend,
        "model": entry,
        "download_requested": False,
        "requires_artifact_verification": tier != "disabled",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selector-json", required=True, type=Path)
    parser.add_argument("--catalog", type=Path, default=Path("config/xodus-ai-model-catalog.json"))
    args = parser.parse_args()
    try:
        result = resolve(load_json(args.selector_json), load_json(args.catalog))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"xodus-ai-resolve-model: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

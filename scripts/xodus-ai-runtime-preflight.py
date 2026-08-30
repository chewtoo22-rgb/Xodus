#!/usr/bin/env python3
"""Fail-closed local inference runtime preflight for Xodus.

Consumes the durable hardware-selection record produced at first boot and reports
whether a local llama.cpp runtime is present. This stage never downloads models,
starts a server, changes drivers, or mutates system configuration.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

SCHEMA = 1
TIERS = {"disabled", "lite", "standard", "performance", "workstation"}
BACKENDS = {"none", "cpu", "cuda", "vulkan"}
ENGINE_NAMES = ("llama-server", "llama-cli")


def _regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def load_selection(path: Path) -> dict:
    if not _regular_file(path):
        raise ValueError("selection must be a regular non-symlink file")
    data = json.loads(path.read_text(encoding="utf-8"))
    if set(data) != {"hardware", "recommendation"}:
        raise ValueError("unexpected selection envelope")
    rec = data["recommendation"]
    if not isinstance(rec, dict):
        raise ValueError("recommendation must be an object")
    required = {"tier", "max_model_class", "preferred_quant", "backend", "reason"}
    if set(rec) != required:
        raise ValueError("unexpected recommendation schema")
    if rec["tier"] not in TIERS or rec["backend"] not in BACKENDS:
        raise ValueError("unsupported tier/backend")
    if rec["tier"] == "disabled" and rec["backend"] != "none":
        raise ValueError("disabled tier must use backend none")
    if rec["tier"] != "disabled" and rec["backend"] == "none":
        raise ValueError("enabled tier requires a backend")
    return data


def find_engine(explicit: str | None) -> str | None:
    if explicit:
        p = Path(explicit)
        return str(p) if _regular_file(p) and os.access(p, os.X_OK) else None
    for name in ENGINE_NAMES:
        found = shutil.which(name)
        if found and _regular_file(Path(found)) and os.access(found, os.X_OK):
            return found
    return None


def backend_probe(backend: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if backend == "cuda" and shutil.which("nvidia-smi") is None:
        warnings.append("cuda_selected_but_nvidia_smi_unavailable")
    elif backend == "vulkan" and shutil.which("vulkaninfo") is None:
        warnings.append("vulkan_selected_but_vulkaninfo_unavailable")
    return backend, warnings


def evaluate(selection: dict, engine: str | None) -> dict:
    rec = selection["recommendation"]
    blockers: list[str] = []
    warnings: list[str] = []
    tier = rec["tier"]
    backend = rec["backend"]

    if tier == "disabled":
        blockers.append("local_ai_disabled_by_hardware_policy")
    elif engine is None:
        blockers.append("llama_cpp_runtime_missing")

    _, backend_warnings = backend_probe(backend)
    warnings.extend(backend_warnings)

    return {
        "schema": SCHEMA,
        "ready": not blockers,
        "hardware_validation_claim": False,
        "network_used": False,
        "tier": tier,
        "backend": backend,
        "engine": engine,
        "blockers": blockers,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", default="/var/lib/xodus/ai/hardware-selection.json")
    parser.add_argument("--output")
    parser.add_argument("--llama-bin")
    args = parser.parse_args()

    try:
        selection = load_selection(Path(args.selection))
        result = evaluate(selection, find_engine(args.llama_bin))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": SCHEMA,
            "ready": False,
            "hardware_validation_claim": False,
            "network_used": False,
            "tier": "unknown",
            "backend": "unknown",
            "engine": None,
            "blockers": ["invalid_hardware_selection"],
            "warnings": [str(exc)[:160]],
        }

    payload = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, out)
    else:
        print(payload, end="")
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

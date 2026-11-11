#!/usr/bin/env python3
"""Build a deterministic, non-executing Xodus Studio install plan.

Xodus Studio is the opt-in game and app development workstation layer. It is
never part of the ISO; a user chooses profiles and this planner resolves them
into the exact pacman argv a future, permission-gated installer may run. The
planner never invokes pacman, never touches the network, and never mutates the
system. The `ai-assist` profile reuses the reviewed Xodus AI tier selector so
the coding assistant follows the same hardware policy as the system assistant.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "studio" / "xodus-studio-manifest.json"
AI_SELECTOR = ROOT / "scripts" / "xodus-ai-select.py"
SCHEMA = 1
KNOWN_GPUS = ("intel", "amd", "nvidia")
# Explicit contract markers, matching the other Xodus planners.
network_used = False
executes_commands = False


def _reject_duplicate_keys(pairs: list) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_manifest(path: Path = MANIFEST) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("studio manifest must be a regular non-symlink file")
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("unsupported studio manifest schema")
    return data


def _load_ai_selector():
    spec = importlib.util.spec_from_file_location("xodus_ai_select", AI_SELECTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("Xodus AI selector is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("xodus_ai_select", module)
    spec.loader.exec_module(module)
    return module


def resolve_profiles(manifest: dict, requested: list[str]) -> list[str]:
    """Expand `requires` transitively; return profiles in manifest order."""
    profiles = manifest["profiles"]
    unknown = sorted(set(requested) - set(profiles))
    if unknown:
        raise ValueError(f"unknown studio profile(s): {', '.join(unknown)}")
    if not requested:
        raise ValueError("select at least one studio profile")
    selected: set[str] = set()
    stack = list(requested)
    while stack:
        name = stack.pop()
        if name in selected:
            continue
        selected.add(name)
        stack.extend(profiles[name]["requires"])
    return [name for name in profiles if name in selected]


def build_plan(
    manifest: dict,
    requested: list[str],
    gpu_vendors: list[str],
    ram_gib: float | None = None,
    vram_gib: float = 0.0,
    cpu_threads: int = 1,
) -> dict:
    vendors = sorted({v.strip().lower() for v in gpu_vendors if v.strip()})
    bad = [v for v in vendors if v not in KNOWN_GPUS]
    if bad:
        raise ValueError(f"unsupported GPU vendor(s): {', '.join(bad)}")

    profiles = resolve_profiles(manifest, requested)
    packages: list[str] = []
    for name in profiles:
        packages.extend(manifest["profiles"][name]["packages"])

    warnings: list[str] = []
    needs_vulkan = "graphics" in profiles
    gpu_packages: list[str] = []
    if needs_vulkan:
        for vendor in vendors:
            gpu_packages.extend(manifest["gpu_vulkan_drivers"][vendor])
        if not vendors:
            warnings.append("No GPU vendor given; Vulkan apps will fall back to software or fail until a driver is installed.")
    packages.extend(gpu_packages)
    unique = sorted(set(packages))

    assistant = {"requested": "ai-assist" in profiles, "enabled": False, "tier": "none", "max_model_class": "none", "reason": "not requested"}
    if assistant["requested"]:
        if ram_gib is None:
            raise ValueError("ai-assist requires --ram-gib so the tier selector can apply its memory policy")
        selector = _load_ai_selector()
        rec = selector.classify(selector.Hardware(ram_gib=ram_gib, vram_gib=vram_gib,
                                                  gpu_vendor=vendors[0] if vendors else "none",
                                                  cpu_threads=cpu_threads))
        assistant.update(enabled=rec.tier != "disabled", tier=rec.tier,
                         max_model_class=rec.max_model_class, reason=rec.reason)
        if rec.tier == "disabled":
            warnings.append("Local coding assistant disabled by the AI tier policy; editor installs without it.")

    return {
        "schema": SCHEMA,
        "profiles": profiles,
        "gpu_vendors": vendors,
        "packages": unique,
        "argv": ["pacman", "-S", "--needed", "--", *unique] if unique else [],
        "ai_assistant": assistant,
        "warnings": warnings,
        "executed": False,
        "network_used": False,
        "requires_user_confirmation": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", action="append", default=[], help="studio profile (repeatable); see --list")
    parser.add_argument("--gpu-vendor", action="append", default=[], help="intel, amd or nvidia (repeatable)")
    parser.add_argument("--ram-gib", type=float)
    parser.add_argument("--vram-gib", type=float, default=0.0)
    parser.add_argument("--cpu-threads", type=int, default=1)
    parser.add_argument("--list", action="store_true", help="list profiles and exit")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    if args.list:
        for name, spec in manifest["profiles"].items():
            print(f"{name:<10} {spec['description']}")
        return 0
    try:
        plan = build_plan(manifest, args.profile, args.gpu_vendor, args.ram_gib, args.vram_gib, args.cpu_threads)
    except ValueError as exc:
        print(f"xodus-studio-plan: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

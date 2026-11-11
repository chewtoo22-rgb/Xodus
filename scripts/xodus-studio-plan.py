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
CONTRACT = ROOT / "qa" / "xodus_studio_contract.py"
SCHEMA = 1
# Preference order when several GPUs exist: the discrete GPU hosts the model.
KNOWN_GPUS = ("nvidia", "amd", "intel")
# Explicit contract markers, matching the other Xodus planners.
network_used = False
executes_commands = False


def _load_module(name: str, path: Path):
    if not path.is_file():
        raise ValueError(f"{path.name} is unavailable; refusing to plan without it")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"{path.name} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


def load_manifest(path: Path = MANIFEST) -> dict:
    """Load the manifest through the fail-closed Studio contract (raises ValueError)."""
    contract = _load_module("xodus_studio_contract", CONTRACT)
    data = contract.load(path)
    contract.validate(data)
    return data


def _load_ai_selector():
    return _load_module("xodus_ai_select", AI_SELECTOR)


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
        if "nvidia" in vendors:
            warnings.append("nvidia-utils needs a matching NVIDIA kernel module (nvidia or nvidia-open) for Vulkan to work.")
    packages.extend(gpu_packages)
    unique = sorted(set(packages))

    assistant = {"requested": "ai-assist" in profiles, "enabled": False, "tier": "none", "max_model_class": "none",
                 "preferred_quant": "none", "backend": "none", "reason": "not requested"}
    if assistant["requested"]:
        if ram_gib is None:
            raise ValueError("ai-assist requires --ram-gib so the tier selector can apply its memory policy")
        selector = _load_ai_selector()
        primary = next((v for v in KNOWN_GPUS if v in vendors), "none")
        rec = selector.classify(selector.Hardware(ram_gib=ram_gib, vram_gib=vram_gib,
                                                  gpu_vendor=primary, cpu_threads=cpu_threads))
        assistant.update(enabled=rec.tier != "disabled", tier=rec.tier, max_model_class=rec.max_model_class,
                         preferred_quant=rec.preferred_quant, backend=rec.backend, reason=rec.reason)
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

    try:
        manifest = load_manifest()
        if args.list:
            for name, spec in manifest["profiles"].items():
                print(f"{name:<10} {spec['description']}")
            return 0
        plan = build_plan(manifest, args.profile, args.gpu_vendor, args.ram_gib, args.vram_gib, args.cpu_threads)
    except ValueError as exc:
        print(f"xodus-studio-plan: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

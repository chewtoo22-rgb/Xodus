#!/usr/bin/env python3
"""Fail-closed contract for the Xodus Studio developer manifest.

Studio stays opt-in (never in the ISO), sources only official Arch repos, and
keeps its profile graph acyclic and duplicate-free so the planner is
deterministic. Package existence is checked separately against live Arch sync
databases by the Xodus Studio workflow (`--print-packages`).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "studio" / "xodus-studio-manifest.json"
EXPECTED_KEYS = {
    "schema",
    "iso_default",
    "network_required_for_planning",
    "hardware_validation_claim",
    "allowed_repos",
    "profiles",
    "gpu_vulkan_drivers",
}
PROFILE_KEYS = {"description", "requires", "packages"}
EXPECTED_GPUS = {"intel", "amd", "nvidia"}
PACKAGE_NAME = re.compile(r"^[a-z0-9@_+][a-z0-9@._+-]*$")
MAX_PACKAGES = 200


class ContractError(Exception):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _package_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
        raise ContractError(f"{where} must be a list of strings")
    for name in value:
        if not PACKAGE_NAME.fullmatch(name):
            raise ContractError(f"{where} has invalid package name {name!r}")
    if len(set(value)) != len(value):
        raise ContractError(f"{where} repeats a package")
    return value


def validate(data: Any) -> list[str]:
    """Validate a parsed manifest; return every package it can request."""
    if not isinstance(data, dict):
        raise ContractError("manifest root must be an object")
    if set(data) != EXPECTED_KEYS:
        raise ContractError(f"manifest keys must be exactly {sorted(EXPECTED_KEYS)}")
    if data["schema"] != 1:
        raise ContractError("schema must equal 1")
    if data["iso_default"] is not False:
        raise ContractError("iso_default must stay false; Studio is opt-in and keeps the ISO lightweight")
    if data["network_required_for_planning"] is not False:
        raise ContractError("planning must stay offline")
    if data["hardware_validation_claim"] is not False:
        raise ContractError("hardware_validation_claim must remain false until evidence exists")
    if data["allowed_repos"] != ["core", "extra"]:
        raise ContractError("allowed_repos must be exactly the official core and extra repositories")

    profiles = data["profiles"]
    if not isinstance(profiles, dict) or not profiles:
        raise ContractError("profiles must be a non-empty object")
    owner: dict[str, str] = {}
    for name, spec in profiles.items():
        if not PACKAGE_NAME.fullmatch(name):
            raise ContractError(f"invalid profile name {name!r}")
        if not isinstance(spec, dict) or set(spec) != PROFILE_KEYS:
            raise ContractError(f"profile {name} keys must be exactly {sorted(PROFILE_KEYS)}")
        if not isinstance(spec["description"], str) or not spec["description"].strip():
            raise ContractError(f"profile {name} needs a description")
        requires = spec["requires"]
        if not isinstance(requires, list) or any(r not in profiles or r == name for r in requires):
            raise ContractError(f"profile {name} requires an unknown profile or itself")
        for pkg in _package_list(spec["packages"], f"profile {name}"):
            if pkg in owner:
                raise ContractError(f"package {pkg} appears in both {owner[pkg]} and {name}")
            owner[pkg] = name

    _reject_cycles(profiles)

    drivers = data["gpu_vulkan_drivers"]
    if not isinstance(drivers, dict) or set(drivers) != EXPECTED_GPUS:
        raise ContractError(f"gpu_vulkan_drivers must cover exactly {sorted(EXPECTED_GPUS)}")
    for vendor, pkgs in drivers.items():
        if not _package_list(pkgs, f"gpu driver {vendor}"):
            raise ContractError(f"gpu driver {vendor} must list a package")
        for pkg in pkgs:
            if pkg in owner:
                raise ContractError(f"driver package {pkg} duplicates profile {owner[pkg]}")

    every = sorted(set(owner) | {p for pkgs in drivers.values() for p in pkgs})
    if len(every) > MAX_PACKAGES:
        raise ContractError(f"manifest exceeds {MAX_PACKAGES} packages")
    return every


def _reject_cycles(profiles: dict[str, Any]) -> None:
    state: dict[str, int] = {}

    def visit(node: str) -> None:
        if state.get(node) == 1:
            raise ContractError(f"profile dependency cycle through {node}")
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in profiles[node]["requires"]:
            visit(dep)
        state[node] = 2

    for name in profiles:
        visit(name)


def load(path: Path = MANIFEST) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ContractError("manifest must be a regular file")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
    except ValueError as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def main(argv: list[str]) -> int:
    try:
        packages = validate(load())
    except ContractError as exc:
        print(f"Xodus Studio contract failed: {exc}", file=sys.stderr)
        return 1
    if "--print-packages" in argv:
        print("\n".join(packages))
    else:
        print(f"Xodus Studio manifest is valid: {len(packages)} official-repo packages, opt-in only.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

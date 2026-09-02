#!/usr/bin/env python3
"""Validate the reviewed X1 first-boot -> AI -> runtime service chain.

This is a pure fixture contract. It does not call systemctl or mutate the host.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED = {
    "xodus-first-boot.service": {"kind": "oneshot", "enabled": True, "after": set(), "requires": set()},
    "xodus-ai-first-boot.service": {"kind": "oneshot", "enabled": True, "after": {"xodus-first-boot.service"}, "requires": {"xodus-first-boot.service"}},
    "xodus-ai-runtime-preflight.service": {"kind": "oneshot", "enabled": True, "after": {"xodus-ai-first-boot.service"}, "requires": {"xodus-ai-first-boot.service"}},
}


def validate(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    units = payload.get("units")
    if not isinstance(units, dict):
        return ["units must be an object"]
    for name, contract in REQUIRED.items():
        unit = units.get(name)
        if not isinstance(unit, dict):
            errors.append(f"missing unit: {name}")
            continue
        if unit.get("kind") != contract["kind"]:
            errors.append(f"{name}: kind must be oneshot")
        if unit.get("enabled") is not True:
            errors.append(f"{name}: must be enabled")
        after = set(unit.get("after", [])) if isinstance(unit.get("after", []), list) else set()
        requires = set(unit.get("requires", [])) if isinstance(unit.get("requires", []), list) else set()
        if not contract["after"].issubset(after):
            errors.append(f"{name}: missing After dependency")
        if not contract["requires"].issubset(requires):
            errors.append(f"{name}: missing Requires dependency")
        if unit.get("network_online") is True:
            errors.append(f"{name}: network-online coupling is forbidden")
        if unit.get("shell_indirection") is True:
            errors.append(f"{name}: shell indirection is forbidden")
    graphical = units.get("graphical.target", {})
    if not isinstance(graphical, dict) or "xodus-first-boot.service" not in set(graphical.get("after", [])):
        errors.append("graphical.target must wait for xodus-first-boot.service")
    return errors


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    errors = validate(payload)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("x1 service chain: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

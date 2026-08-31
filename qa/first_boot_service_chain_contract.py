#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

UNITS = {
    "base": "xodus-first-boot.service",
    "ai": "xodus-ai-first-boot.service",
    "runtime": "xodus-ai-runtime-preflight.service",
}


def parse_unit(path: Path) -> dict[str, list[str]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"unit must be a regular non-symlink file: {path}")
    values: dict[str, list[str]] = {}
    section = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" not in line:
            raise ValueError(f"malformed unit line in {path.name}: {raw!r}")
        key, value = line.split("=", 1)
        values.setdefault(f"{section}.{key.strip()}", []).append(value.strip())
    return values


def require(values: dict[str, list[str]], key: str, expected: str) -> None:
    if expected not in values.get(key, []):
        raise ValueError(f"missing {key}={expected}")


def forbid_tokens(values: dict[str, list[str]], tokens: tuple[str, ...]) -> None:
    for key, items in values.items():
        for item in items:
            lower = item.lower()
            for token in tokens:
                if token in lower:
                    raise ValueError(f"forbidden token {token!r} in {key}")


def validate(root: Path) -> None:
    units = {name: parse_unit(root / filename) for name, filename in UNITS.items()}
    base, ai, runtime = units["base"], units["ai"], units["runtime"]

    for name, unit in units.items():
        require(unit, "Service.Type", "oneshot")
        require(unit, "Service.NoNewPrivileges", "yes")
        require(unit, "Install.WantedBy", "multi-user.target")
        forbid_tokens(unit, ("network-online.target", "curl ", "wget ", "/bin/sh", "bash -c"))

    require(base, "Unit.Before", "graphical.target")
    require(base, "Unit.ConditionPathExists", "!/var/lib/xodus/first-boot/complete")
    require(base, "Service.ExecStart", "/usr/lib/xodus/xodus-first-boot")
    require(base, "Service.ReadWritePaths", "/var/lib/xodus/first-boot")

    require(ai, "Unit.After", "xodus-first-boot.service")
    require(ai, "Unit.ConditionPathExists", "/var/lib/xodus/first-boot/complete")
    require(ai, "Unit.ConditionPathExists", "!/var/lib/xodus/ai/hardware-selection.json")
    require(ai, "Service.ExecStart", "/usr/lib/xodus/xodus-ai-first-boot")
    require(ai, "Service.ReadWritePaths", "/var/lib/xodus/ai")

    require(runtime, "Unit.After", "xodus-ai-first-boot.service")
    require(runtime, "Unit.Requires", "xodus-ai-first-boot.service")
    require(runtime, "Unit.ConditionPathExists", "/var/lib/xodus/ai/hardware-selection.json")
    require(runtime, "Service.ReadWritePaths", "/var/lib/xodus/ai")
    execs = runtime.get("Service.ExecStart", [])
    if len(execs) != 1 or not execs[0].startswith("/usr/bin/python3 /usr/lib/xodus/xodus-ai-runtime-preflight.py "):
        raise ValueError("runtime preflight must execute the fixed Xodus preflight script directly")

    for name, unit in units.items():
        rw = unit.get("Service.ReadWritePaths", [])
        if len(rw) != 1:
            raise ValueError(f"{name} must expose exactly one writable path")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="overlay/first-boot")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: Xodus first-boot service chain contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

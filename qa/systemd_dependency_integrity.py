#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEPENDENCY_KEYS = {"After", "Before", "Requires", "Wants"}
ORDERING_KEYS = {"After", "Before"}


def parse_unit(path: Path) -> dict[str, list[str]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"unit must be a regular non-symlink file: {path}")
    section = ""
    values: dict[str, list[str]] = {}
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


def split_units(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        out.extend(token for token in value.split() if token.endswith(".service"))
    return out


def validate(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"unit root must be a regular directory: {root}")

    paths = sorted(root.glob("xodus-*.service"))
    if not paths:
        raise ValueError("no Xodus service units found")

    units = {path.name: parse_unit(path) for path in paths}
    names = set(units)
    graph: dict[str, set[str]] = {name: set() for name in names}

    for name, values in units.items():
        for key in DEPENDENCY_KEYS:
            refs = split_units(values.get(f"Unit.{key}", []))
            for ref in refs:
                if ref.startswith("xodus-") and ref not in names:
                    raise ValueError(f"{name} references missing Xodus unit {ref} via {key}")
                if ref not in names or key not in ORDERING_KEYS:
                    continue
                if key == "After":
                    graph[name].add(ref)
                else:  # Before=A means A is ordered after this unit.
                    graph[ref].add(name)

    state: dict[str, int] = {name: 0 for name in names}
    stack: list[str] = []

    def visit(node: str) -> None:
        if state[node] == 2:
            return
        if state[node] == 1:
            cycle_start = stack.index(node)
            cycle = stack[cycle_start:] + [node]
            raise ValueError("Xodus service ordering cycle: " + " -> ".join(cycle))
        state[node] = 1
        stack.append(node)
        for dep in sorted(graph[node]):
            visit(dep)
        stack.pop()
        state[node] = 2

    for name in sorted(names):
        visit(name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="overlay/first-boot")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: Xodus systemd dependency integrity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

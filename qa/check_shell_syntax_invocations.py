#!/usr/bin/env python3
"""Reject `bash -n` calls that name more than one script.

`bash -n a.sh b.sh` parses only a.sh; every later operand becomes a positional
argument and is never syntax-checked, so such a gate silently passes broken
scripts. Each script must be checked by its own `bash -n` call (a loop is fine).
"""
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "qa/*.sh",
    "scripts/*.sh",
    "overlay/**/*.sh",
)
INVOCATION = re.compile(r"\bbash\s+-n\b(?P<rest>[^\n]*)")
COMMAND_END = re.compile(r"\s*(?:;|&&|\|\||\||\)|\bdo\b|\bthen\b)")


def operands(rest: str) -> list[str]:
    """Return the operands of one `bash -n` command, up to its terminator."""
    cut = COMMAND_END.search(rest)
    segment = rest[: cut.start()] if cut else rest
    try:
        tokens = shlex.split(segment, comments=True)
    except ValueError:
        tokens = segment.split()
    return tokens


def violations_in(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for match in INVOCATION.finditer(line):
            args = operands(match.group("rest"))
            if len(args) > 1 or any("[@]" in arg or "[*]" in arg for arg in args):
                found.append((lineno, line.strip()))
    return found


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv] if argv else sorted(
        {p for pattern in SCAN_GLOBS for p in ROOT.glob(pattern) if p.is_file()}
    )
    failures = 0
    for path in paths:
        for lineno, line in violations_in(path.read_text(encoding="utf-8")):
            rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            print(f"{rel}:{lineno}: bash -n checks only its first operand: {line}")
            failures += 1
    if failures:
        print(f"Shell syntax invocation contract failed: {failures} multi-operand bash -n call(s).")
        return 1
    print(f"Shell syntax invocation contract passed across {len(paths)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

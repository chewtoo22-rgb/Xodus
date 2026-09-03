#!/usr/bin/env python3
"""Fail-closed static checker for GitHub Actions workflow permissions."""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

FORBIDDEN = re.compile(r"(?:read-all|write-all|\*|contents\s*:\s*write|actions\s*:\s*write|pull-requests\s*:\s*write)")


def main() -> int:
    if not WORKFLOWS.is_dir():
        print("missing .github/workflows", file=sys.stderr)
        return 1

    files = sorted(p for p in WORKFLOWS.iterdir() if p.suffix in {".yml", ".yaml"})
    if not files:
        print("no workflow files found", file=sys.stderr)
        return 1

    failures: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^permissions:\s*$", text) is None:
            failures.append(f"{path.relative_to(ROOT)}: missing top-level permissions block")
            continue
        if re.search(r"(?m)^\s+contents:\s+read\s*$", text) is None:
            failures.append(f"{path.relative_to(ROOT)}: permissions must include contents: read")
        if FORBIDDEN.search(text):
            failures.append(f"{path.relative_to(ROOT)}: forbidden broad or writable permission detected")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    print(f"workflow permission contract passed for {len(files)} workflow(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

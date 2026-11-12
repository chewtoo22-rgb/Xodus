#!/usr/bin/env python3
"""Fail-closed validation for explicit least-privilege GitHub Actions permissions."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

if not WORKFLOWS.is_dir():
    raise SystemExit("missing .github/workflows")

errors = []
workflow_files = sorted(list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml")))
if not workflow_files:
    errors.append("no workflow files found")

for path in workflow_files:
    text = path.read_text(encoding="utf-8")
    if not re.search(r"(?m)^permissions:\s*$", text):
        errors.append(f"{path.relative_to(ROOT)}: missing top-level permissions block")
        continue
    block = re.search(r"(?ms)^permissions:\s*\n(?P<body>(?:^[ \t]+[^\n]*\n?)+)", text)
    body = block.group("body") if block else ""
    if re.search(r"(?mi)^\s{2,}(?:write-all|read-all):\s*(?:true|yes)?\s*$", body):
        errors.append(f"{path.relative_to(ROOT)}: wildcard permissions are forbidden")
    if re.search(r"(?mi)^\s{2,}[^#\n]+:\s*(?:write|true|yes)\s*$", body):
        errors.append(f"{path.relative_to(ROOT)}: writable permission detected")
    if re.search(r"(?mi)^\s{2,}contents:\s*(?:write|read-write)\s*$", body):
        errors.append(f"{path.relative_to(ROOT)}: contents write access is forbidden")

if errors:
    print("workflow permission boundary: FAIL")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print(f"workflow permission boundary: PASS ({len(workflow_files)} workflows checked)")

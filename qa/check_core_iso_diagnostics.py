#!/usr/bin/env python3
"""Fail-closed contract for Core ISO failure diagnostics."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "core-iso-build.yml"
text = WORKFLOW.read_text(encoding="utf-8")

errors = []
required_snippets = {
    "failure diagnostics step": "- name: Preserve failure diagnostics",
    "diagnostics upload step": "- name: Upload failure diagnostics",
    "disk usage capture": "df -h > disk-usage.txt",
    "build file inventory": "find pearos-iso/work -maxdepth 3",
    "build log artifact": "pearos-iso/xodus-build-attempt-*.log",
}
for label, snippet in required_snippets.items():
    if snippet not in text:
        errors.append(f"missing {label}: {snippet}")

if not re.search(r"(?ms)- name: Upload failure diagnostics.*?if-no-files-found: ignore", text):
    errors.append("failure diagnostics upload must tolerate absent optional files")

if errors:
    print("core ISO diagnostics contract: FAIL")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print("core ISO diagnostics contract: PASS")

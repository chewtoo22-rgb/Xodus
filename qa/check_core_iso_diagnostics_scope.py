#!/usr/bin/env python3
"""Fail-closed contract for bounded Core ISO failure diagnostics."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "core-iso-build.yml"
text = WORKFLOW.read_text(encoding="utf-8")
errors = []

required = {
    "failure-only preservation": "- name: Preserve failure diagnostics\n        if: failure()",
    "failure-only upload": "- name: Upload failure diagnostics\n        if: failure()",
    "bounded disk capture": "df -h > disk-usage.txt",
    "bounded inventory": "find pearos-iso/work -maxdepth 3",
    "optional artifact tolerance": "if-no-files-found: ignore",
    "short retention": "retention-days: 7",
}
for label, snippet in required.items():
    if snippet not in text:
        errors.append(f"missing {label}: {snippet}")

if re.search(r"(?ms)- name: Upload failure diagnostics.*?path:.*?(?:^\s{10}\S.*)$", text) and "${{ github.workspace }}" in text:
    errors.append("failure diagnostics must not upload the full workspace")

if re.search(r"(?m)^\s+- name: Upload reference ISO\n(?:(?!^\s+- name:).)*?xodus-core-iso-failure-diagnostics", text):
    errors.append("reference ISO upload must not include failure diagnostics")

if errors:
    print("core ISO diagnostics scope: FAIL")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print("core ISO diagnostics scope: PASS")

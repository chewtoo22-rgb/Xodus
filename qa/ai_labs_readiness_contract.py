#!/usr/bin/env python3
"""Fail-closed contract for the X1 AI Labs foundation manifest."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "qa" / "ai-labs-readiness-manifest.json"
EXPECTED_KEYS = {
    "schema",
    "target",
    "hardware_validation_claim",
    "network_required",
    "checks",
}
EXPECTED_CHECKS = {
    "ai-first-boot-ordering",
    "runtime-preflight-gate",
    "model-cache-is-optional",
    "offline-safe-default",
    "service-health-observable",
}


def fail(message: str) -> None:
    raise SystemExit(f"AI Labs readiness contract failed: {message}")


def main() -> None:
    if not MANIFEST.is_file() or MANIFEST.is_symlink():
        fail("manifest must be a regular file")
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON: {exc}")
    if not isinstance(data, dict):
        fail("manifest root must be an object")
    if set(data) != EXPECTED_KEYS:
        fail(f"manifest keys must be exactly {sorted(EXPECTED_KEYS)}")
    if data["schema"] != 1:
        fail("schema must equal 1")
    if data["target"] != "intel-nuc-x86_64":
        fail("target must be intel-nuc-x86_64")
    if data["hardware_validation_claim"] is not False:
        fail("hardware_validation_claim must remain false until evidence exists")
    if data["network_required"] is not False:
        fail("network_required must remain false for offline-safe first boot")
    checks = data["checks"]
    if not isinstance(checks, list) or set(checks) != EXPECTED_CHECKS or len(checks) != len(EXPECTED_CHECKS):
        fail("checks must match the exact bounded AI Labs prerequisite set")
    print("AI Labs readiness manifest is valid and fail-closed.")


if __name__ == "__main__":
    main()

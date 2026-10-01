#!/usr/bin/env python3
"""Fail-closed validation for the X1 installer/UEFI safety manifest."""
from __future__ import annotations

import json
import sys
from pathlib import Path

MANIFEST = Path(__file__).with_name("x1-installer-uefi-safety-manifest.json")
EXPECTED_KEYS = {"schema", "target", "destructive_install", "hardware_validation_claim", "checks"}
EXPECTED_CHECKS = {
    "dedicated_target_disk_required",
    "uefi_boot_entry_explicit",
    "legacy_csm_not_required",
    "secure_boot_state_recorded",
    "installer_confirmation_required",
    "rollback_path_documented",
}


def fail(message: str) -> None:
    raise SystemExit(f"installer/UEFI safety contract failed: {message}")


def main() -> None:
    if not MANIFEST.is_file() or MANIFEST.is_symlink():
        fail("manifest must be a regular file")
    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"manifest unreadable or invalid JSON: {exc}")
    if not isinstance(payload, dict):
        fail("manifest root must be an object")
    if set(payload) != EXPECTED_KEYS:
        fail(f"top-level keys must be exactly {sorted(EXPECTED_KEYS)}")
    if payload["schema"] != 1:
        fail("schema must equal 1")
    if payload["target"] != "intel-nuc-x86_64":
        fail("target must be intel-nuc-x86_64")
    if payload["destructive_install"] is not False:
        fail("destructive_install must remain false until an approved hardware procedure exists")
    if payload["hardware_validation_claim"] is not False:
        fail("hardware_validation_claim must remain false before physical evidence")
    checks = payload["checks"]
    if not isinstance(checks, dict) or set(checks) != EXPECTED_CHECKS:
        fail(f"checks must contain exactly {sorted(EXPECTED_CHECKS)}")
    if any(value is not True for value in checks.values()):
        fail("every safety prerequisite must be explicitly true")
    print("installer/UEFI safety contract: PASS")


if __name__ == "__main__":
    main()

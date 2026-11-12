#!/usr/bin/env python3
"""Fail-closed contract for the X1 Intel NUC hardware-test readiness manifest."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "qa" / "x1_nuc_readiness_manifest.json"

REQUIRED_CHECKS = {
    "uefi_boot_path",
    "qemu_ovmf_smoke",
    "installer_vm_gate",
    "first_boot_services",
    "ai_first_boot_ordering",
    "recovery_rollback_plan",
    "dedicated_target_disk",
}
ALLOWED_KEYS = {"schema", "milestone", "target", "destructive_install", "hardware_validation_claim", "required_checks"}


def fail(message: str) -> None:
    raise SystemExit(f"X1 NUC readiness contract failed: {message}")


def load() -> dict:
    if not MANIFEST.is_file() or MANIFEST.is_symlink():
        fail("manifest must be a regular file")
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"manifest is not valid UTF-8 JSON: {exc}")
    if not isinstance(data, dict):
        fail("manifest root must be an object")
    return data


def main() -> None:
    data = load()
    if set(data) != ALLOWED_KEYS:
        fail(f"manifest keys must equal {sorted(ALLOWED_KEYS)}")
    if data.get("schema") != 1:
        fail("schema must be integer 1")
    if data.get("milestone") != "X1":
        fail("milestone must be X1")
    if data.get("target") != "intel-nuc-x86_64":
        fail("target must be intel-nuc-x86_64")
    if data.get("destructive_install") is not False:
        fail("destructive_install must remain false until the destructive VM gate passes")
    if data.get("hardware_validation_claim") is not False:
        fail("hardware_validation_claim must remain false before physical NUC evidence exists")
    checks = data.get("required_checks")
    if not isinstance(checks, list) or set(checks) != REQUIRED_CHECKS or len(checks) != len(REQUIRED_CHECKS):
        fail("required_checks must contain the exact bounded X1 readiness set")
    if any(not isinstance(item, str) or not item or item != item.strip() for item in checks):
        fail("required_checks entries must be non-empty strings")
    print("X1 NUC readiness contract: PASS")


if __name__ == "__main__":
    main()

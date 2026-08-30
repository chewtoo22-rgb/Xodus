#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HEX40 = re.compile(r"^[0-9a-f]{40}$")
NUC_KEYS = {
    "schema", "status", "candidate_sha", "boot_mode", "root_source",
    "root_fstype", "root_backing_disk", "first_boot_completed_utc",
    "ai_tier", "ai_backend", "physical_install_claim",
    "hardware_validation_claim",
}
RUNTIME_KEYS = {
    "schema", "ready", "hardware_validation_claim", "network_used", "tier",
    "backend", "engine", "blockers", "warnings",
}


def fail(message: str) -> None:
    raise ValueError(message)


def load_object(path: pathlib.Path) -> dict:
    if path.is_symlink():
        fail(f"symlink not allowed: {path}")
    if not path.is_file():
        fail(f"required evidence missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path.name}") from exc
    if not isinstance(value, dict):
        fail(f"top-level JSON object required in {path.name}")
    return value


def validate(nuc_path: pathlib.Path, runtime_path: pathlib.Path) -> dict:
    nuc = load_object(nuc_path)
    runtime = load_object(runtime_path)

    if set(nuc) != NUC_KEYS:
        fail("unexpected NUC readiness schema")
    if nuc["schema"] != 1 or nuc["status"] != "ready_for_nuc_hardware_test":
        fail("NUC readiness bundle did not pass")
    candidate_sha = nuc["candidate_sha"]
    if not isinstance(candidate_sha, str) or not HEX40.fullmatch(candidate_sha):
        fail("NUC readiness candidate SHA is invalid")
    if nuc["boot_mode"] != "uefi":
        fail("local AI readiness requires UEFI installed boot")
    if nuc["physical_install_claim"] != "not_automatic":
        fail("physical-install claim guard missing")
    if nuc["hardware_validation_claim"] is not False:
        fail("NUC readiness must not claim hardware validation")

    if set(runtime) != RUNTIME_KEYS:
        fail("unexpected local AI runtime schema")
    if runtime["schema"] != 1:
        fail("unsupported local AI runtime schema")
    if runtime["hardware_validation_claim"] is not False:
        fail("runtime preflight must not claim hardware validation")
    if runtime["network_used"] is not False:
        fail("runtime preflight must remain offline")
    if runtime["ready"] is not True:
        fail("local AI runtime preflight is not ready")
    if runtime["blockers"] != []:
        fail("ready runtime evidence cannot contain blockers")
    if not isinstance(runtime["warnings"], list) or not all(isinstance(v, str) for v in runtime["warnings"]):
        fail("runtime warnings must be a string list")

    if runtime["tier"] != nuc["ai_tier"]:
        fail("runtime tier disagrees with first-boot/NUC readiness evidence")
    if runtime["backend"] != nuc["ai_backend"]:
        fail("runtime backend disagrees with first-boot/NUC readiness evidence")
    if runtime["tier"] == "disabled" or runtime["backend"] == "none":
        fail("local AI runtime cannot be ready when hardware policy disables it")

    engine = runtime["engine"]
    if not isinstance(engine, str) or not engine.startswith("/") or len(engine) > 512:
        fail("runtime engine must be a bounded absolute path")

    return {
        "schema": 1,
        "status": "ready_for_nuc_local_ai_test",
        "candidate_sha": candidate_sha,
        "ai_tier": runtime["tier"],
        "ai_backend": runtime["backend"],
        "engine": engine,
        "network_used": False,
        "physical_install_claim": "not_automatic",
        "hardware_validation_claim": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate coherent X1 NUC + local AI runtime readiness evidence")
    parser.add_argument("--nuc-readiness", required=True)
    parser.add_argument("--ai-runtime", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        result = validate(pathlib.Path(args.nuc_readiness), pathlib.Path(args.ai_runtime))
    except (OSError, ValueError) as exc:
        print(f"xodus-x1-local-ai-readiness: FAIL: {exc}", file=sys.stderr)
        return 1

    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        out = pathlib.Path(args.output)
        if out.exists() and out.is_symlink():
            print("xodus-x1-local-ai-readiness: FAIL: output symlink not allowed", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f".{out.name}.tmp")
        tmp.write_text(encoded, encoding="utf-8")
        tmp.replace(out)
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

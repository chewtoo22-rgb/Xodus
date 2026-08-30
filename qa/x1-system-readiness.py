#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HEX40 = re.compile(r"^[0-9a-f]{40}$")
LOCAL_AI_KEYS = {
    "schema", "status", "candidate_sha", "ai_tier", "ai_backend", "engine",
    "network_used", "physical_install_claim", "hardware_validation_claim",
}
DESKTOP_KEYS = {
    "schema", "hardware_validation_claim", "desktop_ready", "blockers", "warnings",
}


def fail(message: str) -> None:
    raise ValueError(message)


def regular_file(path: pathlib.Path) -> None:
    if path.is_symlink():
        fail(f"symlink not allowed: {path}")
    if not path.is_file():
        fail(f"required evidence missing: {path}")


def load_json(path: pathlib.Path) -> dict:
    regular_file(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path.name}") from exc
    if not isinstance(value, dict):
        fail(f"top-level JSON object required in {path.name}")
    return value


def load_kv(path: pathlib.Path) -> dict[str, str]:
    regular_file(path)
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw:
            continue
        if "=" not in raw:
            fail(f"malformed key/value line in {path.name}")
        key, value = raw.split("=", 1)
        if not key or key in out:
            fail(f"duplicate/empty key in {path.name}: {key!r}")
        out[key] = value
    return out


def parse_csv(value: str) -> list[str]:
    if not value:
        return []
    items = value.split(",")
    if any(not item for item in items):
        fail("empty desktop blocker/warning entry")
    return items


def validate(local_ai_path: pathlib.Path, desktop_path: pathlib.Path) -> dict:
    local_ai = load_json(local_ai_path)
    desktop = load_kv(desktop_path)

    if set(local_ai) != LOCAL_AI_KEYS:
        fail("unexpected local AI readiness schema")
    if local_ai["schema"] != 1 or local_ai["status"] != "ready_for_nuc_local_ai_test":
        fail("local AI readiness gate did not pass")
    candidate_sha = local_ai["candidate_sha"]
    if not isinstance(candidate_sha, str) or not HEX40.fullmatch(candidate_sha):
        fail("local AI readiness candidate SHA is invalid")
    if local_ai["network_used"] is not False:
        fail("local AI readiness must remain offline")
    if local_ai["physical_install_claim"] != "not_automatic":
        fail("physical-install claim guard missing")
    if local_ai["hardware_validation_claim"] is not False:
        fail("local AI readiness must not claim hardware validation")
    if local_ai["ai_tier"] == "disabled" or local_ai["ai_backend"] == "none":
        fail("local AI readiness contradicts disabled hardware policy")
    engine = local_ai["engine"]
    if not isinstance(engine, str) or not engine.startswith("/") or len(engine) > 512:
        fail("local AI engine must be a bounded absolute path")

    if set(desktop) != DESKTOP_KEYS:
        fail("unexpected desktop preflight schema")
    if desktop["schema"] != "1":
        fail("unsupported desktop preflight schema")
    if desktop["hardware_validation_claim"] != "false":
        fail("desktop preflight must not claim hardware validation")
    if desktop["desktop_ready"] not in {"true", "false"}:
        fail("desktop_ready must be true or false")
    blockers = parse_csv(desktop["blockers"])
    warnings = parse_csv(desktop["warnings"])
    if desktop["desktop_ready"] != "true":
        fail("desktop preflight is not ready")
    if blockers:
        fail("ready desktop evidence cannot contain blockers")

    return {
        "schema": 1,
        "status": "ready_for_x1_nuc_system_test",
        "candidate_sha": candidate_sha,
        "desktop_ready": True,
        "desktop_warnings": warnings,
        "ai_tier": local_ai["ai_tier"],
        "ai_backend": local_ai["ai_backend"],
        "engine": engine,
        "network_used": False,
        "physical_install_claim": "not_automatic",
        "hardware_validation_claim": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind X1 desktop and local-AI readiness into one NUC system-test gate"
    )
    parser.add_argument("--local-ai-readiness", required=True)
    parser.add_argument("--desktop-preflight", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        result = validate(
            pathlib.Path(args.local_ai_readiness),
            pathlib.Path(args.desktop_preflight),
        )
    except (OSError, ValueError) as exc:
        print(f"xodus-x1-system-readiness: FAIL: {exc}", file=sys.stderr)
        return 1

    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        out = pathlib.Path(args.output)
        if out.exists() and out.is_symlink():
            print("xodus-x1-system-readiness: FAIL: output symlink not allowed", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f".{out.name}.tmp")
        tmp.write_text(encoded, encoding="utf-8")
        tmp.replace(out)
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

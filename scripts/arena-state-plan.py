#!/usr/bin/env python3
"""Pure, non-mutating Arena state-transition planner.

Consumes a trusted snapshot plus requested Arena profile and emits deterministic
enter/restore plans. It never changes system state or executes commands.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

SCHEMA = 1
POWER_PROFILES = {"power-saver", "balanced", "performance"}
AUDIO_PROFILES = {"default", "low-latency"}
AI_STATES = {"active", "yielded"}
ARENA_PROFILES = {"quiet", "balanced", "performance"}
SNAPSHOT_KEYS = {"schema", "power_profile", "audio_profile", "maintenance_paused", "ai_runtime"}
REQUEST_KEYS = {"schema", "arena_profile", "yield_ai"}


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Snapshot:
    power_profile: str
    audio_profile: str
    maintenance_paused: bool
    ai_runtime: str


@dataclass(frozen=True)
class Request:
    arena_profile: str
    yield_ai: bool


def _exact_object(value: Any, allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    unknown = set(value) - allowed
    missing = allowed - set(value)
    if unknown:
        raise ContractError(f"{label} has unknown fields: {sorted(unknown)}")
    if missing:
        raise ContractError(f"{label} missing fields: {sorted(missing)}")
    if value.get("schema") != SCHEMA:
        raise ContractError(f"{label} schema must be {SCHEMA}")
    return value


def parse_snapshot(value: Any) -> Snapshot:
    obj = _exact_object(value, SNAPSHOT_KEYS, "snapshot")
    power = obj["power_profile"]
    audio = obj["audio_profile"]
    maintenance = obj["maintenance_paused"]
    ai_runtime = obj["ai_runtime"]
    if power not in POWER_PROFILES:
        raise ContractError("snapshot power_profile is unsupported")
    if audio not in AUDIO_PROFILES:
        raise ContractError("snapshot audio_profile is unsupported")
    if type(maintenance) is not bool:
        raise ContractError("snapshot maintenance_paused must be boolean")
    if ai_runtime not in AI_STATES:
        raise ContractError("snapshot ai_runtime is unsupported")
    return Snapshot(power, audio, maintenance, ai_runtime)


def parse_request(value: Any) -> Request:
    obj = _exact_object(value, REQUEST_KEYS, "request")
    profile = obj["arena_profile"]
    yield_ai = obj["yield_ai"]
    if profile not in ARENA_PROFILES:
        raise ContractError("request arena_profile is unsupported")
    if type(yield_ai) is not bool:
        raise ContractError("request yield_ai must be boolean")
    return Request(profile, yield_ai)


def _target_power(profile: str) -> str:
    return {
        "quiet": "power-saver",
        "balanced": "balanced",
        "performance": "performance",
    }[profile]


def plan(snapshot_value: Any, request_value: Any) -> dict[str, Any]:
    snapshot = parse_snapshot(snapshot_value)
    request = parse_request(request_value)

    target_power = _target_power(request.arena_profile)
    target_audio = "low-latency" if request.arena_profile == "performance" else "default"
    target_maintenance = request.arena_profile == "performance"
    target_ai = "yielded" if request.yield_ai else snapshot.ai_runtime

    enter: list[dict[str, Any]] = []
    restore: list[dict[str, Any]] = []

    transitions = [
        ("power_profile", snapshot.power_profile, target_power),
        ("audio_profile", snapshot.audio_profile, target_audio),
        ("maintenance_paused", snapshot.maintenance_paused, target_maintenance),
        ("ai_runtime", snapshot.ai_runtime, target_ai),
    ]
    for key, before, after in transitions:
        if before != after:
            enter.append({"set": key, "from": before, "to": after})
            restore.insert(0, {"set": key, "from": after, "to": before})

    return {
        "schema": SCHEMA,
        "arena_profile": request.arena_profile,
        "hardware_validation_claim": False,
        "mutates_system": False,
        "enter": enter,
        "restore": restore,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot")
    parser.add_argument("request")
    args = parser.parse_args()
    try:
        with open(args.snapshot, "r", encoding="utf-8") as handle:
            snapshot = json.load(handle)
        with open(args.request, "r", encoding="utf-8") as handle:
            request = json.load(handle)
        print(json.dumps(plan(snapshot, request), sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        print(f"arena-state-plan: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fail-closed admission for Xodus Arena Mode performance profiles.

This module is intentionally pure: it validates and normalizes requested Arena
policy without executing commands or mutating system state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import re
from typing import Any, Mapping

SCHEMA_VERSION = 1
ALLOWED_FIELDS = {
    "schema_version",
    "profile",
    "cpu_governor",
    "gpu_policy",
    "frame_limit_hz",
    "display_refresh_hz",
    "audio_low_latency",
    "local_ai_yield",
}
PROFILE_DEFAULTS = {
    "quiet": {
        "cpu_governor": "powersave",
        "gpu_policy": "powersave",
        "frame_limit_hz": 60,
        "display_refresh_hz": 60,
        "audio_low_latency": False,
        "local_ai_yield": True,
    },
    "balanced": {
        "cpu_governor": "schedutil",
        "gpu_policy": "auto",
        "frame_limit_hz": 120,
        "display_refresh_hz": 120,
        "audio_low_latency": True,
        "local_ai_yield": True,
    },
    "performance": {
        "cpu_governor": "performance",
        "gpu_policy": "performance",
        "frame_limit_hz": 144,
        "display_refresh_hz": 144,
        "audio_low_latency": True,
        "local_ai_yield": True,
    },
}
PROFILE_IDENTITY_FIELDS = (
    "cpu_governor",
    "gpu_policy",
    "audio_low_latency",
    "local_ai_yield",
)
CPU_GOVERNORS = {"powersave", "schedutil", "performance"}
GPU_POLICIES = {"powersave", "auto", "performance"}
PROFILE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class ArenaProfileError(ValueError):
    pass


@dataclass(frozen=True)
class ArenaProfile:
    schema_version: int
    profile: str
    cpu_governor: str
    gpu_policy: str
    frame_limit_hz: int
    display_refresh_hz: int
    audio_low_latency: bool
    local_ai_yield: bool
    mutates_system: bool = False
    executes_process: bool = False
    hardware_validation_claim: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def _bounded_int(name: str, value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArenaProfileError(f"{name} must be an integer")
    if not math.isfinite(float(value)) or not minimum <= value <= maximum:
        raise ArenaProfileError(f"{name} must be between {minimum} and {maximum}")
    return value


def _require_profile_identity(name: str, raw: Mapping[str, Any], defaults: Mapping[str, Any]) -> None:
    """Prevent overrides from turning a named profile into a contradictory policy.

    Frame/refresh tuning remains adjustable within the global safety bounds, but
    policy-defining fields are part of the profile identity and must match the
    reviewed defaults exactly.
    """

    for field in PROFILE_IDENTITY_FIELDS:
        if field in raw and raw[field] != defaults[field]:
            raise ArenaProfileError(f"{field} conflicts with {name} profile")


def admit_profile(raw: Mapping[str, Any]) -> ArenaProfile:
    if not isinstance(raw, Mapping):
        raise ArenaProfileError("profile must be an object")

    unknown = set(raw) - ALLOWED_FIELDS
    if unknown:
        raise ArenaProfileError(f"unknown fields: {', '.join(sorted(unknown))}")

    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ArenaProfileError("unsupported schema_version")

    name = raw.get("profile")
    if not isinstance(name, str) or not PROFILE_RE.fullmatch(name):
        raise ArenaProfileError("invalid profile name")
    if name not in PROFILE_DEFAULTS:
        raise ArenaProfileError("unsupported profile")

    defaults = PROFILE_DEFAULTS[name]
    _require_profile_identity(name, raw, defaults)

    values = dict(defaults)
    for key in values:
        if key in raw:
            values[key] = raw[key]

    cpu = values["cpu_governor"]
    gpu = values["gpu_policy"]
    if cpu not in CPU_GOVERNORS:
        raise ArenaProfileError("unsupported cpu_governor")
    if gpu not in GPU_POLICIES:
        raise ArenaProfileError("unsupported gpu_policy")

    frame = _bounded_int("frame_limit_hz", values["frame_limit_hz"], 30, 240)
    refresh = _bounded_int("display_refresh_hz", values["display_refresh_hz"], 30, 240)
    if frame > refresh:
        raise ArenaProfileError("frame_limit_hz cannot exceed display_refresh_hz")

    audio = values["audio_low_latency"]
    ai_yield = values["local_ai_yield"]
    if not isinstance(audio, bool) or not isinstance(ai_yield, bool):
        raise ArenaProfileError("boolean policy fields must be booleans")

    return ArenaProfile(
        schema_version=SCHEMA_VERSION,
        profile=name,
        cpu_governor=cpu,
        gpu_policy=gpu,
        frame_limit_hz=frame,
        display_refresh_hz=refresh,
        audio_low_latency=audio,
        local_ai_yield=ai_yield,
    )


def main() -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Validate an Arena Mode profile")
    parser.add_argument("profile_json", type=Path)
    args = parser.parse_args()

    path = args.profile_json
    if path.is_symlink() or not path.is_file():
        parser.error("profile_json must be a regular non-symlink file")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        admitted = admit_profile(raw)
    except (OSError, json.JSONDecodeError, ArenaProfileError) as exc:
        parser.error(str(exc))
    print(admitted.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

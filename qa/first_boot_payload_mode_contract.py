#!/usr/bin/env python3
"""Validate the shipped first-boot payload boundary without executing it."""
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "overlay" / "first-boot"

RUNNERS = ("xodus-first-boot", "xodus-ai-first-boot")
UNITS = (
    "xodus-first-boot.service",
    "xodus-ai-first-boot.service",
    "xodus-ai-runtime-preflight.service",
)


def fail(message: str) -> None:
    raise SystemExit(f"first-boot payload contract failed: {message}")


def require_regular(name: str) -> Path:
    path = PAYLOAD / name
    if not path.exists():
        fail(f"missing {path}")
    if path.is_symlink() or not path.is_file():
        fail(f"{name} must be a regular non-symlink file")
    return path


def main() -> None:
    for name in RUNNERS:
        path = require_regular(name)
        if not (path.stat().st_mode & stat.S_IXUSR):
            fail(f"runner {name} is not owner-executable")

    for name in UNITS:
        path = require_regular(name)
        if path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            fail(f"unit {name} must not be executable")

    first_boot = (PAYLOAD / "xodus-first-boot.service").read_text(encoding="utf-8")
    ai_first_boot = (PAYLOAD / "xodus-ai-first-boot.service").read_text(encoding="utf-8")
    runtime = (PAYLOAD / "xodus-ai-runtime-preflight.service").read_text(encoding="utf-8")

    if "ExecStart=/usr/lib/xodus/xodus-first-boot" not in first_boot:
        fail("base service is not bound to the shipped base runner")
    if "ExecStart=/usr/lib/xodus/xodus-ai-first-boot" not in ai_first_boot:
        fail("AI service is not bound to the shipped AI runner")
    if "After=xodus-ai-first-boot.service" not in runtime:
        fail("runtime preflight does not wait for AI first-boot")
    if "Requires=xodus-ai-first-boot.service" not in runtime:
        fail("runtime preflight does not require AI first-boot")

    print("first-boot payload contract: PASS")


if __name__ == "__main__":
    main()

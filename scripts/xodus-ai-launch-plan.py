#!/usr/bin/env python3
"""Build a deterministic, non-executing llama.cpp launch plan for Xodus X1.

This planner consumes already-validated local-AI readiness evidence and a local
GGUF model. It never starts a process, downloads content, opens sockets, or
changes system state. The output is a bounded argv contract for a later service
or session manager to execute after its own policy checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SCHEMA = 1
HEX40 = re.compile(r"^[0-9a-f]{40}$")
READINESS_KEYS = {
    "schema", "status", "candidate_sha", "ai_tier", "ai_backend", "engine",
    "network_used", "physical_install_claim", "hardware_validation_claim",
}
TIERS = {"lite", "standard", "performance", "workstation"}
BACKENDS = {"cpu", "cuda", "vulkan"}
CTX_BY_TIER = {
    "lite": 4096,
    "standard": 8192,
    "performance": 16384,
    "workstation": 32768,
}
MAX_MODEL_BYTES = 128 * 1024 * 1024 * 1024


def fail(message: str) -> None:
    raise ValueError(message)


def regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def load_readiness(path: Path) -> dict:
    if not regular_file(path):
        fail("readiness evidence must be a regular non-symlink file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("malformed readiness JSON") from exc
    if not isinstance(value, dict) or set(value) != READINESS_KEYS:
        fail("unexpected local AI readiness schema")
    if value["schema"] != 1 or value["status"] != "ready_for_nuc_local_ai_test":
        fail("local AI readiness did not pass")
    if not isinstance(value["candidate_sha"], str) or not HEX40.fullmatch(value["candidate_sha"]):
        fail("candidate SHA is invalid")
    if value["ai_tier"] not in TIERS or value["ai_backend"] not in BACKENDS:
        fail("unsupported AI tier/backend")
    if value["network_used"] is not False:
        fail("readiness evidence must remain offline")
    if value["physical_install_claim"] != "not_automatic":
        fail("physical-install claim guard missing")
    if value["hardware_validation_claim"] is not False:
        fail("hardware-validation claim guard missing")
    engine = value["engine"]
    if not isinstance(engine, str) or not engine.startswith("/") or len(engine) > 512:
        fail("engine path must be bounded and absolute")
    if Path(engine).name != "llama-server":
        fail("launch planning requires llama-server")
    return value


def validate_model(path: Path) -> tuple[int, str]:
    if not path.is_absolute():
        fail("model path must be absolute")
    if path.suffix.lower() != ".gguf":
        fail("model must be a GGUF file")
    if not regular_file(path):
        fail("model must be a regular non-symlink file")
    size = path.stat().st_size
    if size <= 0 or size > MAX_MODEL_BYTES:
        fail("model size is outside supported bounds")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return size, digest.hexdigest()


def build_plan(readiness: dict, model: Path, host: str, port: int) -> dict:
    if host not in {"127.0.0.1", "::1"}:
        fail("local inference must bind to loopback")
    if not isinstance(port, int) or isinstance(port, bool) or port < 1024 or port > 65535:
        fail("port must be in the unprivileged range 1024..65535")
    size, digest = validate_model(model)
    ctx = CTX_BY_TIER[readiness["ai_tier"]]
    argv = [
        readiness["engine"],
        "--model", str(model),
        "--host", host,
        "--port", str(port),
        "--ctx-size", str(ctx),
    ]
    return {
        "schema": SCHEMA,
        "status": "ready_for_local_launch",
        "candidate_sha": readiness["candidate_sha"],
        "ai_tier": readiness["ai_tier"],
        "ai_backend": readiness["ai_backend"],
        "engine": readiness["engine"],
        "model": str(model),
        "model_bytes": size,
        "model_sha256": digest,
        "bind_host": host,
        "port": port,
        "context_tokens": ctx,
        "argv": argv,
        "network_downloads_allowed": False,
        "mutates_system": False,
        "executes_process": False,
        "hardware_validation_claim": False,
    }


def publish_plan(out: Path, payload: str) -> None:
    """Publish a new launch-plan artifact without overwrite or partial-write risk."""
    parent = out.parent
    if out.exists() or out.is_symlink():
        fail("output path already exists")
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        fail("output parent must be an existing non-symlink directory")

    fd = -1
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{out.name}.", suffix=".tmp", dir=parent)
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", closefd=True) as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, out)
        tmp_name = None
        dir_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a non-executing Xodus local-AI launch plan")
    parser.add_argument("--readiness", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        readiness = load_readiness(Path(args.readiness))
        plan = build_plan(readiness, Path(args.model), args.host, args.port)
        payload = json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output:
            publish_plan(Path(args.output), payload)
    except (OSError, ValueError) as exc:
        print(f"xodus-ai-launch-plan: FAIL: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

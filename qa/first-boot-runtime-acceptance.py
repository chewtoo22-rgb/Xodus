#!/usr/bin/env python3
import argparse
import json
import math
import pathlib
import re
import sys
from datetime import datetime, timezone

LIVE_FSTYPES = {"overlay", "squashfs", "erofs", "tmpfs", "rootfs"}
LIVE_SOURCE_PATTERNS = (re.compile(r"airootfs", re.I), re.compile(r"^/dev/loop"), re.compile(r"^/dev/mapper/ventoy", re.I))
HEX40 = re.compile(r"^[0-9a-f]{40}$")
TIERS = {"disabled", "lite", "standard", "performance", "workstation"}
BACKENDS = {"none", "cpu", "cuda", "vulkan"}
MAX_VENDOR_LEN = 64
MAX_CPU_THREADS = 4096

def fail(msg: str) -> None:
    raise ValueError(msg)

def regular_file(path: pathlib.Path) -> None:
    if path.is_symlink():
        fail(f"symlink not allowed: {path}")
    if not path.is_file():
        fail(f"required file missing: {path}")

def parse_kv(path: pathlib.Path) -> dict[str, str]:
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

def parse_utc(value: str) -> str:
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid completed UTC timestamp") from exc
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def validate(root: pathlib.Path) -> dict:
    root = root.resolve(strict=True)
    fb = root / "var/lib/xodus/first-boot"
    complete = parse_kv(fb / "complete")
    system = parse_kv(fb / "system.env")
    selection_path = root / "var/lib/xodus/ai/hardware-selection.json"
    regular_file(selection_path)

    if complete != {"schema": "1", "completed_utc": complete.get("completed_utc", "")}:
        fail("unexpected first-boot completion schema")
    completed_utc = parse_utc(complete["completed_utc"])

    required_system = {
        "XODUS_FIRST_BOOT_SCHEMA",
        "XODUS_FIRST_BOOT_COMPLETED_UTC",
        "XODUS_ROOT_SOURCE",
        "XODUS_ROOT_FSTYPE",
        "XODUS_FIRMWARE",
        "XODUS_UPSTREAM_COMMIT",
    }
    if set(system) != required_system:
        fail("unexpected first-boot system snapshot schema")
    if system["XODUS_FIRST_BOOT_SCHEMA"] != "1":
        fail("unsupported first-boot system schema")
    if parse_utc(system["XODUS_FIRST_BOOT_COMPLETED_UTC"]) != completed_utc:
        fail("first-boot completion timestamps disagree")
    if system["XODUS_ROOT_FSTYPE"].lower() in LIVE_FSTYPES:
        fail("live/ephemeral root filesystem rejected")
    source = system["XODUS_ROOT_SOURCE"]
    if not source:
        fail("installed root source is empty")
    if any(p.search(source) for p in LIVE_SOURCE_PATTERNS):
        fail("live root source rejected")
    if system["XODUS_FIRMWARE"].lower() != "uefi":
        fail("X1 first-boot acceptance requires UEFI")
    upstream = system["XODUS_UPSTREAM_COMMIT"]
    if upstream != "unknown" and not HEX40.fullmatch(upstream):
        fail("invalid upstream commit provenance")

    try:
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid hardware selection JSON") from exc
    if set(selection) != {"hardware", "recommendation"}:
        fail("unexpected hardware selection envelope")
    hw = selection["hardware"]
    rec = selection["recommendation"]
    if not isinstance(hw, dict) or set(hw) != {"ram_gib", "vram_gib", "gpu_vendor", "cpu_threads"}:
        fail("unexpected hardware selection schema")
    if not isinstance(rec, dict) or set(rec) != {"tier", "max_model_class", "preferred_quant", "backend", "reason"}:
        fail("unexpected recommendation schema")
    if isinstance(hw["cpu_threads"], bool) or not isinstance(hw["cpu_threads"], int):
        fail("invalid cpu_threads")
    if hw["cpu_threads"] < 1 or hw["cpu_threads"] > MAX_CPU_THREADS:
        fail(f"cpu_threads must be between 1 and {MAX_CPU_THREADS}")
    for key in ("ram_gib", "vram_gib"):
        value = hw[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            fail(f"invalid {key}")
        if not math.isfinite(float(value)) or value < 0:
            fail(f"invalid {key}")
    vendor = hw["gpu_vendor"]
    if not isinstance(vendor, str) or not vendor.strip():
        fail("invalid gpu_vendor")
    if len(vendor.strip()) > MAX_VENDOR_LEN:
        fail("gpu_vendor is too long")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in vendor):
        fail("gpu_vendor contains control characters")
    if rec["tier"] not in TIERS:
        fail("invalid recommendation tier")
    if rec["backend"] not in BACKENDS:
        fail("invalid recommendation backend")
    if rec["tier"] == "disabled" and rec["backend"] != "none":
        fail("disabled AI tier must use backend none")
    if rec["tier"] != "disabled" and rec["backend"] == "none":
        fail("enabled AI tier cannot use backend none")
    for key in ("max_model_class", "preferred_quant", "reason"):
        if not isinstance(rec[key], str) or not rec[key].strip():
            fail(f"invalid recommendation field: {key}")

    return {
        "schema": 1,
        "status": "pass",
        "first_boot_completed_utc": completed_utc,
        "firmware": "uefi",
        "root_source": source,
        "root_fstype": system["XODUS_ROOT_FSTYPE"],
        "ai_tier": rec["tier"],
        "ai_backend": rec["backend"],
        "hardware_validation_claim": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Xodus X1 installed first-boot runtime postconditions")
    parser.add_argument("--root", default="/", help="installed root or fixture root")
    parser.add_argument("--output", help="optional JSON output path")
    args = parser.parse_args()
    try:
        result = validate(pathlib.Path(args.root))
    except (OSError, ValueError) as exc:
        print(f"xodus-first-boot-runtime-acceptance: FAIL: {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        out = pathlib.Path(args.output)
        if out.exists() and out.is_symlink():
            print("xodus-first-boot-runtime-acceptance: FAIL: output symlink not allowed", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f".{out.name}.tmp")
        tmp.write_text(encoded, encoding="utf-8")
        tmp.replace(out)
    sys.stdout.write(encoded)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

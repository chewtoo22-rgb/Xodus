#!/usr/bin/env python3
"""Deterministic first-boot AI tier selector for Xodus.

The selector deliberately recommends a capability tier, not a downloadable model URL.
A separately reviewed model catalog maps tiers to validated artifacts. This keeps
hardware policy testable and prevents first boot from inventing compatibility.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path


MAX_VENDOR_LEN = 64
MAX_CPU_THREADS = 4096
# Explicit contract markers consumed by the offline-boundary QA gate.
network_used = False
hardware_validation_claim = False


@dataclass(frozen=True)
class Hardware:
    ram_gib: float
    vram_gib: float = 0.0
    gpu_vendor: str = "none"
    cpu_threads: int = 1


@dataclass(frozen=True)
class Recommendation:
    tier: str
    max_model_class: str
    preferred_quant: str
    backend: str
    reason: str


def _validate_hardware(hw: Hardware) -> tuple[float, float, str]:
    """Validate hardware observations before they can influence model selection."""
    ram = float(hw.ram_gib)
    vram = float(hw.vram_gib)
    if not math.isfinite(ram) or ram < 0.0:
        raise ValueError("RAM must be a finite non-negative GiB value")
    if not math.isfinite(vram) or vram < 0.0:
        raise ValueError("VRAM must be a finite non-negative GiB value")
    if isinstance(hw.cpu_threads, bool) or not isinstance(hw.cpu_threads, int):
        raise ValueError("CPU thread count must be an integer")
    if hw.cpu_threads < 1 or hw.cpu_threads > MAX_CPU_THREADS:
        raise ValueError(f"CPU thread count must be between 1 and {MAX_CPU_THREADS}")

    vendor = hw.gpu_vendor.strip().lower()
    if len(vendor) > MAX_VENDOR_LEN:
        raise ValueError("GPU vendor string is too long")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in vendor):
        raise ValueError("GPU vendor string contains control characters")
    return ram, vram, vendor


def classify(hw: Hardware) -> Recommendation:
    """Return a conservative tier using validated resources available to local inference."""
    ram, vram, vendor = _validate_hardware(hw)

    if ram < 7.0:
        return Recommendation("disabled", "none", "none", "none",
                              "Less than 7 GiB RAM; local LLM disabled to protect system responsiveness.")

    if ram >= 64.0 and vram >= 16.0:
        return Recommendation("workstation", "20B-30B", "Q4_K_M", _backend(vendor),
                              "64+ GiB RAM and 16+ GiB VRAM support the workstation catalog.")

    if ram >= 32.0 and vram >= 8.0:
        return Recommendation("performance", "7B-14B", "Q4_K_M", _backend(vendor),
                              "32+ GiB RAM and 8+ GiB VRAM support larger local models.")

    if ram >= 16.0:
        return Recommendation("standard", "3B-4B", "Q4_K_M", _backend(vendor),
                              "16+ GiB RAM supports the standard low-memory local model catalog.")

    return Recommendation("lite", "1B-3B", "Q4_K_M", _backend(vendor),
                          "7-16 GiB RAM requires the lightweight local model catalog.")


def _backend(vendor: str) -> str:
    if "nvidia" in vendor:
        return "cuda"
    if "amd" in vendor or "advanced micro" in vendor:
        return "vulkan"
    if "intel" in vendor:
        return "vulkan"
    return "cpu"


def detect_ram_gib() -> float:
    text = Path("/proc/meminfo").read_text(encoding="utf-8")
    match = re.search(r"^MemTotal:\s+(\d+)\s+kB$", text, re.MULTILINE)
    if not match:
        raise RuntimeError("MemTotal unavailable")
    return int(match.group(1)) / 1024 / 1024


def detect_gpu() -> tuple[str, float]:
    """Best-effort detection. Unknown VRAM stays zero and therefore fails conservative gates."""
    drm = Path("/sys/class/drm")
    vendors = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}
    if not drm.exists():
        return "none", 0.0
    for card in sorted(drm.glob("card[0-9]*")):
        vendor_file = card / "device/vendor"
        if not vendor_file.exists():
            continue
        vendor = vendors.get(vendor_file.read_text().strip().lower(), "unknown")
        # amdgpu commonly exposes this. Other drivers remain conservative at 0.
        vram_file = card / "device/mem_info_vram_total"
        vram = 0.0
        if vram_file.exists():
            try:
                vram = int(vram_file.read_text().strip()) / 1024**3
            except ValueError:
                pass
        return vendor, vram
    return "none", 0.0


def detect() -> Hardware:
    vendor, vram = detect_gpu()
    return Hardware(detect_ram_gib(), vram, vendor, os.cpu_count() or 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ram-gib", type=float, help="override detected RAM for testing")
    parser.add_argument("--vram-gib", type=float, default=None, help="override detected VRAM")
    parser.add_argument("--gpu-vendor", default=None, help="override GPU vendor")
    args = parser.parse_args()
    detected = detect()
    hw = Hardware(
        args.ram_gib if args.ram_gib is not None else detected.ram_gib,
        args.vram_gib if args.vram_gib is not None else detected.vram_gib,
        args.gpu_vendor if args.gpu_vendor is not None else detected.gpu_vendor,
        detected.cpu_threads,
    )
    try:
        recommendation = classify(hw)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "hardware": asdict(hw),
        "recommendation": asdict(recommendation),
        "network_used": network_used,
        "hardware_validation_claim": hardware_validation_claim,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

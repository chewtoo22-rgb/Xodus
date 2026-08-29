#!/usr/bin/env python3
"""Deterministic first-boot AI tier selector for Xodus.

The selector deliberately recommends a capability tier, not a downloadable model URL.
A separately reviewed model catalog maps tiers to validated artifacts. This keeps
hardware policy testable and prevents first boot from inventing compatibility.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


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


def classify(hw: Hardware) -> Recommendation:
    """Return a conservative tier using resources available to local inference."""
    ram = max(0.0, hw.ram_gib)
    vram = max(0.0, hw.vram_gib)
    vendor = hw.gpu_vendor.strip().lower()

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
    print(json.dumps({"hardware": asdict(hw), "recommendation": asdict(classify(hw))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

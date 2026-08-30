#!/usr/bin/env python3
import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/xodus-ai-runtime-preflight.py"


def selection(tier="standard", backend="vulkan"):
    return {
        "hardware": {"cpu_threads": 8, "gpu_vendor": "intel", "ram_gib": 31.2, "vram_gib": 0.0},
        "recommendation": {
            "backend": backend,
            "max_model_class": "3B-4B" if tier != "disabled" else "none",
            "preferred_quant": "Q4_K_M" if tier != "disabled" else "none",
            "reason": "test",
            "tier": tier,
        },
    }


def run(sel, engine=True):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sel_path = root / "selection.json"
        out_path = root / "readiness.json"
        sel_path.write_text(json.dumps(sel), encoding="utf-8")
        cmd = ["python3", str(SCRIPT), "--selection", str(sel_path), "--output", str(out_path)]
        if engine:
            fake = root / "llama-cli"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            cmd += ["--llama-bin", str(fake)]
        proc = subprocess.run(cmd, text=True, capture_output=True)
        data = json.loads(out_path.read_text(encoding="utf-8"))
        return proc.returncode, data


def main():
    rc, data = run(selection())
    assert rc == 0 and data["ready"] is True
    assert data["tier"] == "standard" and data["backend"] == "vulkan"
    assert data["network_used"] is False and data["hardware_validation_claim"] is False
    assert data["engine"].endswith("llama-cli")

    rc, data = run(selection(), engine=False)
    assert rc == 2 and data["ready"] is False
    assert data["blockers"] == ["llama_cpp_runtime_missing"]

    rc, data = run(selection("disabled", "none"), engine=False)
    assert rc == 2 and data["blockers"] == ["local_ai_disabled_by_hardware_policy"]

    bad = selection()
    bad["recommendation"]["backend"] = "magic"
    rc, data = run(bad)
    assert rc == 2 and data["blockers"] == ["invalid_hardware_selection"]
    assert data["tier"] == "unknown"

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        real = root / "real.json"
        real.write_text(json.dumps(selection()), encoding="utf-8")
        link = root / "selection.json"
        link.symlink_to(real)
        out = root / "out.json"
        proc = subprocess.run(["python3", str(SCRIPT), "--selection", str(link), "--output", str(out)], text=True)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert proc.returncode == 2 and data["blockers"] == ["invalid_hardware_selection"]

    unit = (REPO / "overlay/first-boot/xodus-ai-runtime-preflight.service").read_text(encoding="utf-8")
    assert "After=xodus-ai-first-boot.service" in unit
    assert "ConditionPathExists=/var/lib/xodus/ai/hardware-selection.json" in unit
    assert "NoNewPrivileges=yes" in unit and "ProtectSystem=strict" in unit
    assert "ReadWritePaths=/var/lib/xodus/ai" in unit

    source = SCRIPT.read_text(encoding="utf-8").lower()
    for forbidden in ("curl ", "wget ", "git clone", "pip install", "http://", "https://"):
        assert forbidden not in source

    print("AI runtime preflight contract: PASS")


if __name__ == "__main__":
    main()

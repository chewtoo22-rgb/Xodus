#!/usr/bin/env python3
"""Static contract for the X1 local-AI offline boundary."""
from __future__ import annotations

import pathlib
import re
import sys

AI_SCRIPTS = (
    pathlib.Path("scripts/xodus-ai-select.py"),
    pathlib.Path("scripts/xodus-ai-launch-plan.py"),
    pathlib.Path("scripts/xodus-ai-runtime-preflight.py"),
)
FORBIDDEN = re.compile(
    r"(?:\b(?:curl|wget|nc|netcat|socat|ftp|telnet)\b|\brequests\b|\burllib\b|\bsocket\b|\bhttpx\b|\bsubprocess\.run\s*\(\s*\[?\s*[\"'](?:curl|wget))",
    re.IGNORECASE,
)
REQUIRED_MARKERS = ("network_used", "hardware_validation_claim")


def main() -> int:
    errors: list[str] = []
    for path in AI_SCRIPTS:
        if not path.is_file():
            errors.append(f"missing AI script: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in REQUIRED_MARKERS:
            if marker not in text:
                errors.append(f"{path}: missing explicit marker {marker}")
        for match in FORBIDDEN.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path}:{line}: forbidden network primitive/import: {match.group(0)!r}")
    if errors:
        print("X1 AI offline boundary: FAIL")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("X1 AI offline boundary: PASS")
    print(f"checked_scripts={len(AI_SCRIPTS)}")
    print("network_policy=offline")
    print("hardware_validation_claim=explicit")
    return 0


if __name__ == "__main__":
    sys.exit(main())

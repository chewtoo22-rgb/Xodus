#!/usr/bin/env python3
"""Static contract for the X1 local-AI offline boundary."""
from __future__ import annotations

import ast
import pathlib
import re
import sys

AI_SCRIPTS = (
    pathlib.Path("scripts/xodus-ai-select.py"),
    pathlib.Path("scripts/xodus-ai-launch-plan.py"),
    pathlib.Path("scripts/xodus-ai-runtime-preflight.py"),
    pathlib.Path("scripts/xodus-ai-resolve-model.py"),
    pathlib.Path("scripts/xodus-ai-verify-artifact.py"),
)
FORBIDDEN = re.compile(
    r"(?:\b(?:curl|wget|nc|netcat|socat|ftp|telnet)\b|\brequests\b|\burllib\b|\bsocket\b|\bhttpx\b|\bsubprocess\.run\s*\(\s*\[?\s*[\"'](?:curl|wget))",
    re.IGNORECASE,
)
REQUIRED_MARKERS = ("network_used", "hardware_validation_claim")

# Trust-boundary scripts get a strict import allowlist instead of a denylist:
# http.client, ssl, ftplib, asyncio or a computed __import__ would all slip past
# FORBIDDEN, so anything not listed here fails.
ALLOWLISTED_SCRIPTS = (
    pathlib.Path("scripts/xodus-ai-resolve-model.py"),
    pathlib.Path("scripts/xodus-ai-verify-artifact.py"),
)
ALLOWED_IMPORTS = frozenset({
    "__future__", "argparse", "dataclasses", "errno", "hashlib", "hmac", "importlib.util",
    "json", "math", "os", "pathlib", "re", "stat", "sys", "typing",
})
# Builtins that run or import code when called by bare name (re.compile is fine),
# plus import entry points reachable as attributes.
FORBIDDEN_BUILTIN_CALLS = frozenset({"__import__", "exec", "eval", "compile"})
FORBIDDEN_ATTRIBUTE_CALLS = frozenset({"__import__", "import_module"})


def allowlist_errors(path: pathlib.Path, text: str) -> list[str]:
    """Return import/dynamic-execution violations for an allowlisted script."""
    errors: list[str] = []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"{path}: cannot parse: {exc}"]
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                errors.append(f"{path}:{node.lineno}: relative imports are not allowed")
                continue
            names = [node.module or ""]
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_BUILTIN_CALLS:
                errors.append(f"{path}:{node.lineno}: dynamic code/import call {func.id!r} is not allowed")
            elif isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRIBUTE_CALLS:
                errors.append(f"{path}:{node.lineno}: dynamic import call {func.attr!r} is not allowed")
        for name in names:
            if name not in ALLOWED_IMPORTS:
                errors.append(f"{path}:{node.lineno}: import {name!r} is not on the offline allowlist")
    return errors


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
        if path in ALLOWLISTED_SCRIPTS:
            errors.extend(allowlist_errors(path, text))
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

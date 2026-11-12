#!/usr/bin/env python3
"""Fail-closed contract for the Xodus Studio project templates.

Every template directory under `studio/templates/` must be declared in
`templates.json` with exactly the files it contains (no extras, no symlinks,
no special files), must only require existing Studio profiles, and must carry
the project-name placeholder in exactly the files the manifest says. Smoke
metadata is argv-only (never a shell string) and may only name packages the
template's Studio profiles would install. The scaffolder
(`scripts/xodus-studio-new.py`) refuses to run unless this contract passes.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "studio" / "templates"
MANIFEST_NAME = "templates.json"
STUDIO_MANIFEST = ROOT / "studio" / "xodus-studio-manifest.json"
PLACEHOLDER = "__XODUS_PROJECT_NAME__"
TOKEN = re.compile(r"__XODUS_[A-Z0-9_]*__")
EXPECTED_KEYS = {"schema", "placeholder", "network_required", "templates"}
TEMPLATE_KEYS = {"description", "profiles", "files", "placeholder_files", "smoke"}
SMOKE_KEYS = {"tools", "packages", "pkg_config_modules", "steps"}
TEMPLATE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
PATH_PART = re.compile(r"^\.?[A-Za-z0-9_][A-Za-z0-9_.-]*$")
TOOL_NAME = re.compile(r"^[a-z][a-z0-9_+-]*$")
# Smoke steps may only invoke build tools; a shell or interpreter here would
# turn the argv-only rule back into arbitrary shell strings.
ALLOWED_TOOLS = frozenset({"cargo", "cc", "cmake", "godot", "luajit", "ninja", "pkg-config"})
# Unicode bidirectional controls ("Trojan Source") make reviewed text differ from what runs.
BIDI_CONTROLS = frozenset(chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))
PACKAGE_NAME = re.compile(r"^[a-z0-9@_+][a-z0-9@._+-]*$")
SMOKE_ARG = re.compile(r"^[A-Za-z0-9_.:/=+-]+$")
MAX_FILE_BYTES = 64 * 1024
MAX_SOURCE_LINES = 150  # per template, README.md excluded


class ContractError(ValueError):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _exact_keys(obj: Any, expected: set[str], where: str) -> None:
    if not isinstance(obj, dict):
        raise ContractError(f"{where} must be an object")
    missing, unexpected = sorted(expected - set(obj)), sorted(set(obj) - expected)
    if missing or unexpected:
        raise ContractError(f"{where} keys mismatch: missing {missing}, unexpected {unexpected}")


def _string_list(value: Any, where: str, pattern: re.Pattern[str], *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(type(v) is str for v in value):
        raise ContractError(f"{where} must be a list of strings")
    if not value and not allow_empty:
        raise ContractError(f"{where} must not be empty")
    for item in value:
        if not pattern.fullmatch(item):
            raise ContractError(f"{where} has invalid entry {item!r}")
    if len(set(value)) != len(value):
        raise ContractError(f"{where} repeats an entry")
    return value


def _relative_path(text: str, where: str) -> None:
    pure = PurePosixPath(text)
    if pure.is_absolute() or not pure.parts or str(pure) != text:
        raise ContractError(f"{where}: {text!r} is not a normalised relative path")
    for index, part in enumerate(pure.parts):
        if part in (".", "..") or not PATH_PART.fullmatch(part):
            raise ContractError(f"{where}: {text!r} has an invalid path component {part!r}")
        if part.lower() == ".git" or (part.startswith(".") and index < len(pure.parts) - 1):
            raise ContractError(f"{where}: {text!r} must not create .git or hidden directories")
    if PLACEHOLDER in text:
        raise ContractError(f"{where}: file paths must not contain the placeholder")


def load_studio_profiles(path: Path = STUDIO_MANIFEST) -> dict[str, Any]:
    """Load and validate the Studio manifest; return its profiles."""
    sys.path.insert(0, str(ROOT / "qa"))
    try:
        import xodus_studio_contract as studio  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    try:
        data = studio.load(path)
        studio.validate(data)
    except studio.ContractError as exc:
        raise ContractError(f"studio manifest invalid: {exc}") from exc
    return data["profiles"]


def profile_closure(profiles: dict[str, Any], requested: list[str]) -> tuple[set[str], set[str]]:
    """Return (profiles, packages) reached from `requested` through `requires`."""
    seen: set[str] = set()
    stack = list(requested)
    while stack:
        name = stack.pop()
        if name not in seen:
            seen.add(name)
            stack.extend(profiles[name]["requires"])
    packages = {pkg for name in seen for pkg in profiles[name]["packages"]}
    return seen, packages


def scan_directory(directory: Path) -> set[str]:
    """Return every regular file under `directory` (posix relative paths); reject anything else."""
    if directory.is_symlink() or not directory.is_dir():
        raise ContractError(f"{directory.name} must be a real directory")
    found: set[str] = set()
    for current, dirs, files in os.walk(directory, followlinks=False):
        base = Path(current)
        for name in sorted(dirs):
            if (base / name).is_symlink():
                raise ContractError(f"symlinked directory in template: {(base / name).relative_to(directory)}")
        for name in files:
            path = base / name
            mode = os.lstat(path).st_mode
            rel = path.relative_to(directory).as_posix()
            if stat.S_ISLNK(mode):
                raise ContractError(f"symlink in template: {rel}")
            if not stat.S_ISREG(mode):
                raise ContractError(f"non-regular file in template: {rel}")
            found.add(rel)
    return found


def read_template_file(path: Path, where: str) -> str:
    mode = os.lstat(path).st_mode
    if not stat.S_ISREG(mode):
        raise ContractError(f"{where} must be a regular file")
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ContractError(f"{where} exceeds {MAX_FILE_BYTES} bytes")
    if b"\0" in raw or b"\r" in raw:
        raise ContractError(f"{where} must be LF-terminated text without NUL bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError(f"{where} is not UTF-8") from exc
    if any(ch in BIDI_CONTROLS for ch in text):
        raise ContractError(f"{where} contains Unicode bidirectional control characters")
    return text


def validate(data: Any, root: Path = TEMPLATES_DIR, studio_profiles: dict[str, Any] | None = None) -> list[str]:
    """Validate the parsed manifest against `root`; return every smoke package."""
    _exact_keys(data, EXPECTED_KEYS, "templates manifest")
    if type(data["schema"]) is not int or data["schema"] != 1:
        raise ContractError("schema must equal 1")
    if data["placeholder"] != PLACEHOLDER:
        raise ContractError(f"placeholder must be exactly {PLACEHOLDER}")
    if data["network_required"] is not False:
        raise ContractError("network_required must stay false; scaffolding is offline")
    templates = data["templates"]
    if not isinstance(templates, dict) or not templates:
        raise ContractError("templates must be a non-empty object")
    if list(templates) != sorted(templates):
        raise ContractError("templates must be sorted by id")
    profiles = load_studio_profiles() if studio_profiles is None else studio_profiles

    if root.is_symlink() or not root.is_dir():
        raise ContractError("templates root must be a real directory")
    entries = {p.name: p for p in root.iterdir()}
    for name, path in entries.items():
        if path.is_symlink():
            raise ContractError(f"symlink in templates root: {name}")
    stray = sorted(n for n, p in entries.items() if n != MANIFEST_NAME and not p.is_dir())
    if stray:
        raise ContractError(f"unexpected files in templates root: {stray}")
    dirs = {n for n, p in entries.items() if p.is_dir()}
    if dirs != set(templates):
        raise ContractError(f"template directories {sorted(dirs)} do not match manifest ids {sorted(templates)}")

    every_package: set[str] = set()
    for tid, spec in templates.items():
        where = f"template {tid}"
        if not TEMPLATE_ID.fullmatch(tid):
            raise ContractError(f"invalid template id {tid!r}")
        _exact_keys(spec, TEMPLATE_KEYS, where)
        if type(spec["description"]) is not str or not spec["description"].strip():
            raise ContractError(f"{where} needs a description")

        requested = _string_list(spec["profiles"], f"{where} profiles", PACKAGE_NAME)
        unknown = sorted(set(requested) - set(profiles))
        if unknown:
            raise ContractError(f"{where} requires unknown studio profile(s): {unknown}")
        _, available = profile_closure(profiles, requested)

        files = _string_list(spec["files"], f"{where} files", re.compile(r".+"))
        for name in files:
            _relative_path(name, f"{where} files")
        if files != sorted(files):
            raise ContractError(f"{where} files must be sorted")
        if "README.md" not in files:
            raise ContractError(f"{where} must ship README.md")
        actual = scan_directory(root / tid)
        if actual != set(files):
            raise ContractError(f"{where} files mismatch: missing {sorted(set(files) - actual)}, "
                                f"unlisted {sorted(actual - set(files))}")

        marked = _string_list(spec["placeholder_files"], f"{where} placeholder_files", re.compile(r".+"))
        if marked != sorted(marked) or not set(marked) <= set(files):
            raise ContractError(f"{where} placeholder_files must be a sorted subset of files")
        if "README.md" not in marked:
            raise ContractError(f"{where} README.md must name the project via the placeholder")
        source_lines = 0
        carrying: set[str] = set()
        for name in files:
            text = read_template_file(root / tid / name, f"{where} {name}")
            stray_tokens = sorted(set(TOKEN.findall(text)) - {PLACEHOLDER})
            if stray_tokens:
                raise ContractError(f"{where} {name} has unknown token(s) {stray_tokens}")
            if PLACEHOLDER in text:
                carrying.add(name)
            if name != "README.md":
                source_lines += text.count("\n")
        if carrying != set(marked):
            raise ContractError(f"{where} placeholder expected in {sorted(marked)} but found in {sorted(carrying)}")
        if source_lines > MAX_SOURCE_LINES:
            raise ContractError(f"{where} has {source_lines} source lines; keep templates under {MAX_SOURCE_LINES}")

        smoke = spec["smoke"]
        _exact_keys(smoke, SMOKE_KEYS, f"{where} smoke")
        tools = _string_list(smoke["tools"], f"{where} smoke tools", TOOL_NAME)
        disallowed = sorted(set(tools) - ALLOWED_TOOLS)
        if disallowed:
            raise ContractError(f"{where} smoke tools {disallowed} are not allowed build tools")
        packages = _string_list(smoke["packages"], f"{where} smoke packages", PACKAGE_NAME)
        outside = sorted(set(packages) - available)
        if outside:
            raise ContractError(f"{where} smoke packages {outside} are not installed by profiles {requested}")
        _string_list(smoke["pkg_config_modules"], f"{where} smoke pkg_config_modules", PACKAGE_NAME,
                     allow_empty=True)
        if smoke["pkg_config_modules"] and "pkg-config" not in tools:
            raise ContractError(f"{where} probes pkg-config modules without listing the pkg-config tool")
        steps = smoke["steps"]
        if not isinstance(steps, list) or not steps:
            raise ContractError(f"{where} smoke steps must be a non-empty list")
        for step in steps:
            if not isinstance(step, list) or not step or not all(type(a) is str for a in step):
                raise ContractError(f"{where} smoke step must be a non-empty argv list")
            if step[0] not in tools:
                raise ContractError(f"{where} smoke step runs {step[0]!r}, which is not a listed tool")
            for arg in step:
                if not SMOKE_ARG.fullmatch(arg) or ".." in arg or arg.startswith("/"):
                    raise ContractError(f"{where} smoke argument {arg!r} is not allowed")
        every_package.update(packages)
    return sorted(every_package)


def load(path: Path = TEMPLATES_DIR / MANIFEST_NAME) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ContractError("templates manifest must be a regular file")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
    except ValueError as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def main(argv: list[str]) -> int:
    try:
        data = load()
        packages = validate(data)
    except ContractError as exc:
        print(f"Xodus Studio templates contract failed: {exc}", file=sys.stderr)
        return 1
    if "--print-packages" in argv:
        print("\n".join(packages))
    elif "--print-ids" in argv:
        print("\n".join(data["templates"]))
    else:
        print(f"Xodus Studio templates are valid: {len(data['templates'])} templates, "
              f"{len(packages)} smoke packages, offline scaffolding only.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

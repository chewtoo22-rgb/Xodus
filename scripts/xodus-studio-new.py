#!/usr/bin/env python3
"""Scaffold a new Xodus Studio project from a reviewed template.

The scaffolder copies one template from `studio/templates/` into a new or
empty directory, replacing the project-name placeholder. It loads templates
only through the fail-closed templates contract, validates the project name
strictly, refuses to overwrite anything or follow a symlinked destination,
never runs a build or any other program, and never touches the network. It
prints a JSON summary; `--dry-run` prints the same plan without writing.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "qa" / "xodus_studio_templates_contract.py"
TEMPLATES_DIR = ROOT / "studio" / "templates"
SCHEMA = 1
# Lowercase ASCII, starts with a letter: valid as a Cargo package, CMake
# project, Godot project name and file name. No dots, slashes or leading '-'.
NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")
NAME_MAX = 48
# Names Cargo refuses as package names (Rust keywords and the built-in `test`
# crate), plus Rust's reserved words. Rejected for every template so a project
# name stays portable across templates.
RESERVED_NAMES = frozenset({
    "test", "abstract", "as", "async", "await", "become", "box", "break", "const", "continue",
    "crate", "do", "dyn", "else", "enum", "extern", "false", "final", "fn", "for", "gen", "if",
    "impl", "in", "let", "loop", "macro", "match", "mod", "move", "mut", "override", "priv",
    "pub", "ref", "return", "self", "static", "struct", "super", "trait", "true", "try",
    "type", "typeof", "unsafe", "unsized", "use", "virtual", "where", "while", "yield",
    # Cargo forbids binary targets that collide with its build directory names.
    "build", "deps", "examples", "incremental",
})
# Explicit contract markers, matching the other Xodus planners.
network_used = False
executes_commands = False


def _load_contract():
    if not CONTRACT.is_file():
        raise ValueError("templates contract is unavailable; refusing to scaffold without it")
    spec = importlib.util.spec_from_file_location("xodus_studio_templates_contract", CONTRACT)
    if spec is None or spec.loader is None:
        raise ValueError("templates contract cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("xodus_studio_templates_contract", module)
    spec.loader.exec_module(module)
    return module


def load_manifest(root: Path = TEMPLATES_DIR) -> dict:
    """Load templates through the fail-closed contract (raises ValueError)."""
    contract = _load_contract()
    data = contract.load(root / contract.MANIFEST_NAME)
    contract.validate(data, root=root)
    return data


def validate_name(name: str) -> str:
    if type(name) is not str or not 1 <= len(name) <= NAME_MAX:
        raise ValueError(f"project name must be 1-{NAME_MAX} characters")
    if not name.isascii() or any(ch not in NAME_CHARS for ch in name):
        raise ValueError("project name may only use lowercase ASCII letters, digits, '_' and '-'")
    if not name[0].isalpha():
        raise ValueError("project name must start with a lowercase letter")
    if name.endswith("-"):
        raise ValueError("project name must not end with '-'")
    if name.replace("-", "_") in RESERVED_NAMES:
        raise ValueError(f"project name {name!r} is a reserved word (Cargo refuses it)")
    return name


def _check_dest(dest: Path, templates_root: Path) -> None:
    if dest.is_symlink():
        raise ValueError(f"destination {dest} is a symlink; refusing to follow it")
    if dest.exists():
        if not dest.is_dir():
            raise ValueError(f"destination {dest} exists and is not a directory")
        if any(dest.iterdir()):
            raise ValueError(f"destination {dest} is not empty; refusing to overwrite")
    resolved = dest.resolve()
    templates = templates_root.resolve()
    if resolved == templates or templates in resolved.parents:
        raise ValueError("destination must not be inside the template tree")


def render(manifest: dict, template_id: str, name: str, root: Path = TEMPLATES_DIR) -> list[tuple[str, bytes]]:
    templates = manifest["templates"]
    if template_id not in templates:
        raise ValueError(f"unknown template {template_id!r}; see --list")
    validate_name(name)
    placeholder = manifest["placeholder"]
    out = []
    for rel in templates[template_id]["files"]:
        text = (root / template_id / rel).read_text(encoding="utf-8")
        rendered = text.replace(placeholder, name)
        if placeholder in rendered:
            raise ValueError(f"placeholder survived substitution in {rel}")
        out.append((rel, rendered.encode("utf-8")))
    return out


def build_plan(manifest: dict, template_id: str, name: str, dest: Path,
               root: Path = TEMPLATES_DIR) -> tuple[dict, list[tuple[str, bytes]]]:
    files = render(manifest, template_id, name, root)
    _check_dest(dest, root)
    spec = manifest["templates"][template_id]
    plan = {
        "schema": SCHEMA,
        "template": template_id,
        "name": name,
        "dest": str(dest),
        "profiles": list(spec["profiles"]),
        "install_hint": ["scripts/xodus-studio-plan.py", *[a for p in spec["profiles"] for a in ("--profile", p)]],
        "files": [{"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                  for rel, data in files],
        "smoke": {"tools": list(spec["smoke"]["tools"]), "steps": [list(s) for s in spec["smoke"]["steps"]]},
        "written": False,
        "executed": False,
        "network_used": False,
    }
    return plan, files


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _open_child_dir(parent_fd: int, name: str, create: bool) -> int:
    if create:
        os.mkdir(name, 0o755, dir_fd=parent_fd)
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise ValueError(f"refusing to write through non-directory or symlink {name!r}") from exc


def write_files(dest: Path, files: list[tuple[str, bytes]]) -> None:
    """Create every file exclusively, relative to one opened destination handle.

    The destination's final component is opened with O_NOFOLLOW and every
    subdirectory and file is created relative to that handle (dir_fd), so the
    tree cannot be redirected by swapping a path for a symlink between checks
    and writes. Parent components of --dest are resolved normally.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    parent_fd = os.open(dest.parent, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0))
    try:
        try:
            os.mkdir(dest.name, 0o755, dir_fd=parent_fd)
        except FileExistsError:
            pass
        root_fd = _open_child_dir(parent_fd, dest.name, create=False)
    finally:
        os.close(parent_fd)
    try:
        if os.listdir(root_fd):
            raise ValueError(f"destination {dest} is not empty; refusing to overwrite")
        made: dict[tuple[str, ...], int] = {(): root_fd}
        try:
            for rel, data in files:
                parts = tuple(rel.split("/"))
                for depth in range(1, len(parts)):
                    key = parts[:depth]
                    if key not in made:
                        made[key] = _open_child_dir(made[key[:-1]], key[-1], create=True)
                fd = os.open(parts[-1], _FILE_FLAGS, 0o644, dir_fd=made[parts[:-1]])
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
        finally:
            for key, fd in made.items():
                if key:
                    os.close(fd)
    finally:
        os.close(root_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template", help="template id; see --list")
    parser.add_argument("--name", help="project name: lowercase letters, digits, '_' or '-', starting with a letter")
    parser.add_argument("--dest", help="new or empty directory to create the project in")
    parser.add_argument("--list", action="store_true", help="list templates and exit")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without writing files")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest()
        if args.list:
            for tid, spec in manifest["templates"].items():
                print(f"{tid:<14} [{', '.join(spec['profiles'])}] {spec['description']}")
            return 0
        if not args.template or args.name is None or not args.dest:
            raise ValueError("--template, --name and --dest are required (or use --list)")
        dest = Path(args.dest)
        plan, files = build_plan(manifest, args.template, args.name, dest)
        if not args.dry_run:
            write_files(dest, files)
            plan["written"] = True
    except (ValueError, OSError) as exc:
        print(f"xodus-studio-new: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

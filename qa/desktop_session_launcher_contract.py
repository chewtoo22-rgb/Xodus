#!/usr/bin/env python3
"""Fail-closed integrity checks for installed X/Wayland session launchers.

This validator is intentionally read-only.  It does not start a display manager,
execute a session, modify the installed root, or claim physical hardware
validation.  It answers a narrower question: does every discovered session
entry resolve to a bounded executable inside the inspected root without shell
indirection or path escape?
"""

from __future__ import annotations

import argparse
import os
import shlex
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MAX_DESKTOP_BYTES = 64 * 1024
SESSION_DIRS = ("usr/share/wayland-sessions", "usr/share/xsessions")
SAFE_COMMAND_DIRS = ("usr/bin", "usr/local/bin", "bin")
SHELL_WRAPPERS = {
    "sh",
    "bash",
    "dash",
    "zsh",
    "fish",
    "csh",
    "tcsh",
    "env",
}


class DesktopSessionContractError(ValueError):
    pass


@dataclass(frozen=True)
class SessionLauncher:
    entry: str
    command: str
    resolved_command: str


def _inside_root(root: Path, candidate: Path) -> Path:
    root_resolved = root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise DesktopSessionContractError(
            f"launcher escapes installed root: {candidate} -> {resolved}"
        ) from exc
    return resolved


def _read_exec(entry: Path) -> str:
    try:
        info = entry.lstat()
    except FileNotFoundError as exc:
        raise DesktopSessionContractError(f"session entry disappeared: {entry}") from exc

    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise DesktopSessionContractError(f"session entry must be a regular non-symlink file: {entry}")
    if info.st_size <= 0 or info.st_size > MAX_DESKTOP_BYTES:
        raise DesktopSessionContractError(f"session entry size out of bounds: {entry}")

    text = entry.read_text(encoding="utf-8")
    if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in text):
        raise DesktopSessionContractError(f"session entry contains control characters: {entry}")

    in_desktop_entry = False
    exec_values: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_desktop_entry = line == "[Desktop Entry]"
            continue
        if in_desktop_entry and line.startswith("Exec="):
            exec_values.append(line[5:].strip())

    if len(exec_values) != 1 or not exec_values[0]:
        raise DesktopSessionContractError(
            f"session entry must contain exactly one non-empty Exec in [Desktop Entry]: {entry}"
        )
    return exec_values[0]


def _resolve_command(root: Path, exec_value: str) -> tuple[str, Path]:
    if "\n" in exec_value or "\r" in exec_value or "\x00" in exec_value:
        raise DesktopSessionContractError("Exec contains control characters")
    try:
        argv = shlex.split(exec_value, posix=True)
    except ValueError as exc:
        raise DesktopSessionContractError(f"Exec is not valid shell-like token syntax: {exc}") from exc
    if not argv:
        raise DesktopSessionContractError("Exec has no command")

    command = argv[0]
    command_name = Path(command).name
    if command_name in SHELL_WRAPPERS:
        raise DesktopSessionContractError(f"shell/interpreter wrapper is not allowed: {command_name}")

    if command.startswith("/"):
        candidate = root / command.lstrip("/")
        resolved = _inside_root(root, candidate)
    elif "/" in command:
        raise DesktopSessionContractError(f"relative command path is not allowed: {command}")
    else:
        resolved = None
        for rel_dir in SAFE_COMMAND_DIRS:
            candidate = root / rel_dir / command
            if candidate.exists() or candidate.is_symlink():
                resolved = _inside_root(root, candidate)
                break
        if resolved is None:
            raise DesktopSessionContractError(f"session command is not installed in a safe command directory: {command}")

    mode = resolved.stat().st_mode
    if not stat.S_ISREG(mode) or not os.access(resolved, os.X_OK):
        raise DesktopSessionContractError(f"resolved session command is not an executable regular file: {resolved}")
    return command, resolved


def validate_root(root: Path) -> list[SessionLauncher]:
    if not root.is_dir():
        raise DesktopSessionContractError(f"installed root is not a directory: {root}")
    root = root.resolve(strict=True)

    entries: list[Path] = []
    for rel_dir in SESSION_DIRS:
        session_dir = root / rel_dir
        if not session_dir.exists():
            continue
        info = session_dir.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise DesktopSessionContractError(f"session directory must be a real directory: {session_dir}")
        entries.extend(sorted(session_dir.glob("*.desktop")))

    if not entries:
        raise DesktopSessionContractError("no desktop session entries found")

    launchers: list[SessionLauncher] = []
    for entry in entries:
        exec_value = _read_exec(entry)
        command, resolved = _resolve_command(root, exec_value)
        launchers.append(
            SessionLauncher(
                entry=str(entry.relative_to(root)),
                command=command,
                resolved_command="/" + str(resolved.relative_to(root)),
            )
        )
    return launchers


def _print_result(launchers: Iterable[SessionLauncher]) -> None:
    launchers = list(launchers)
    print("schema=1")
    print("hardware_validation_claim=false")
    print("mutates_system=false")
    print("executes_process=false")
    print(f"session_entries={len(launchers)}")
    for index, launcher in enumerate(launchers, start=1):
        print(f"session_{index}_entry={launcher.entry}")
        print(f"session_{index}_command={launcher.command}")
        print(f"session_{index}_resolved={launcher.resolved_command}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/"))
    args = parser.parse_args()
    try:
        launchers = validate_root(args.root)
    except DesktopSessionContractError as exc:
        parser.error(str(exc))
    _print_result(launchers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

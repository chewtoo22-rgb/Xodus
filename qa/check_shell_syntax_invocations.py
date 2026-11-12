#!/usr/bin/env python3
"""Reject `bash -n` / `sh -n` calls that can name more than one script.

Why this exists: `bash -n a.sh b.sh` parses only a.sh. Every later operand
becomes a positional argument and is never syntax-checked, so such a gate
silently passes broken scripts. Each script must be checked by its own
`bash -n` call (a loop is fine).

Flagged: more than one operand, array expansions ("${x[@]}"), unquoted globs
(*.sh) and unquoted variables ($scripts), which can all expand to several
files. Redirections, `--`, pipes and command separators end the operand list.
"""
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "qa/*.sh",
    "scripts/*.sh",
    "overlay/**/*",
)
SHELL_WORD = re.compile(r"(?<![\w./-])(?:bash|sh)(?![\w.-])")
SHEBANG = re.compile(r"^#!.*\b(?:bash|sh)\b")
TERMINATORS = {";", ";;", "&", "&&", "||", "|", "|&", "(", ")", "do", "then", "done", "fi", "}"}
OPTIONS_WITH_ARGUMENT = {"-O", "+O", "-o", "+o"}


def _strip_command_substitutions(text: str) -> str:
    """Replace each balanced $(...) with a placeholder word."""
    out: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            out.append("CMDSUB")
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _tokens(segment: str) -> list[str]:
    lexer = shlex.shlex(_strip_command_substitutions(segment), posix=False, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        return list(lexer)
    except ValueError:  # unbalanced quotes: fall back to whitespace words
        return segment.split()


def _is_quoted(token: str) -> bool:
    return token[:1] in {'"', "'"}


def _syntax_check_operands(tokens: list[str]) -> list[str] | None:
    """Given tokens after the shell word, return operands if this is a -n check."""
    i, noexec = 0, False
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--":
            i += 1
            break
        if tok in OPTIONS_WITH_ARGUMENT:
            i += 2
            continue
        if re.fullmatch(r"[-+][A-Za-z]+", tok):
            if "c" in tok[1:]:
                return None  # command string, not a file check
            noexec = noexec or (tok[0] == "-" and "n" in tok[1:])
            i += 1
            continue
        if tok.startswith("--"):
            i += 1
            continue
        break
    if not noexec:
        return None
    operands: list[str] = []
    for j in range(i, len(tokens)):
        tok = tokens[j]
        if tok in TERMINATORS or tok[0] in "<>;&|()":
            break
        if tok.isdigit() and j + 1 < len(tokens) and tokens[j + 1][:1] in "<>":
            break
        operands.append(tok)
    return operands


def _expands_to_many(token: str) -> bool:
    if "[@]" in token or "[*]" in token:
        return True
    if _is_quoted(token):
        return False
    return any(ch in token for ch in "*?") or token.startswith("$") and not token.startswith("$(")


def violations_in(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for match in SHELL_WORD.finditer(line):
            operands = _syntax_check_operands(_tokens(line[match.end():]))
            if operands is None:
                continue
            if len(operands) > 1 or any(_expands_to_many(op) for op in operands):
                found.append((lineno, line.strip()))
                break
    return found


def _is_shell_file(path: Path) -> bool:
    if path.suffix in {".yml", ".yaml", ".sh"}:
        return True
    try:
        with path.open("r", encoding="utf-8") as handle:
            return bool(SHEBANG.match(handle.readline()))
    except (OSError, UnicodeDecodeError):
        return False


def main(argv: list[str]) -> int:
    paths = [Path(p).resolve() for p in argv] if argv else sorted(
        {p for pattern in SCAN_GLOBS for p in ROOT.glob(pattern) if p.is_file() and _is_shell_file(p)}
    )
    failures = 0
    for path in paths:
        for lineno, line in violations_in(path.read_text(encoding="utf-8")):
            rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            print(f"{rel}:{lineno}: bash -n checks only its first operand: {line}")
            failures += 1
    if failures:
        print(f"Shell syntax invocation contract failed: {failures} multi-operand bash -n call(s).")
        return 1
    print(f"Shell syntax invocation contract passed across {len(paths)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

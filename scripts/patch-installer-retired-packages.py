#!/usr/bin/env python3
"""Remove only known-retired nonessential Plasma packages from a qualified installer.

This transform exists for the X1 destructive-install proof because the pinned pearOS
installer still names two packages that are no longer present in the current Arch
repositories: plasma-disks and plasma-sdk. The transform is deliberately narrow:
it requires each retired package to appear exactly once as a standalone package-list
entry, removes only those two entries, refuses malformed/drifted input, and leaves all
other package names and installer logic byte-for-byte unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

RETIRED_PACKAGES = ("plasma-disks", "plasma-sdk")
PACKAGE_LINE = re.compile(r"^(?P<indent>[ \t]*)(?P<name>[A-Za-z0-9@._+:-]+)(?P<suffix>[ \t]*)$")


def patch(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines(keepends=True)
    counts = {name: 0 for name in RETIRED_PACKAGES}
    removed: list[str] = []
    output: list[str] = []

    for line in lines:
        body = line[:-1] if line.endswith("\n") else line
        if body.endswith("\r"):
            body = body[:-1]
        match = PACKAGE_LINE.fullmatch(body)
        if match and match.group("name") in counts:
            name = match.group("name")
            counts[name] += 1
            removed.append(name)
            continue
        output.append(line)

    unexpected = {name: count for name, count in counts.items() if count != 1}
    if unexpected:
        detail = ", ".join(f"{name}={count}" for name, count in sorted(unexpected.items()))
        raise ValueError(
            "retired-package contract changed; expected exactly one standalone entry each: "
            + detail
        )

    patched = "".join(output)
    for name in RETIRED_PACKAGES:
        if re.search(rf"(?m)^[ \t]*{re.escape(name)}[ \t]*$", patched):
            raise AssertionError(f"retired package remained after patch: {name}")

    return patched, removed


def self_test() -> None:
    fixture = """BASE_PACKAGES=(\n  plasma-desktop\n  plasma-disks\n  plasma-sdk\n  sddm\n)\necho plasma-sdk-is-not-a-package-entry\n"""
    patched, removed = patch(fixture)
    assert removed == ["plasma-disks", "plasma-sdk"]
    assert "  plasma-desktop\n" in patched
    assert "  sddm\n" in patched
    assert "echo plasma-sdk-is-not-a-package-entry\n" in patched
    assert "  plasma-disks\n" not in patched
    assert "  plasma-sdk\n" not in patched

    for broken in (
        fixture.replace("  plasma-sdk\n", ""),
        fixture.replace("  plasma-sdk\n", "  plasma-sdk\n  plasma-sdk\n"),
    ):
        try:
            patch(broken)
        except ValueError:
            pass
        else:
            raise AssertionError("drifted retired-package fixture did not fail closed")

    print("retired_package_patch_self_test=pass")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?")
    parser.add_argument("output", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    if not args.input or not args.output:
        parser.error("input and output are required unless --self-test is used")

    src = Path(args.input)
    dst = Path(args.output)
    original = src.read_text()
    patched, removed = patch(original)
    dst.write_text(patched)
    dst.chmod(0o700)

    print(f"input_sha256={hashlib.sha256(original.encode()).hexdigest()}")
    print(f"output_sha256={hashlib.sha256(patched.encode()).hexdigest()}")
    print("retired_packages_removed=" + ",".join(removed))
    print("retired_package_policy=exact-two-known-nonessential-plasma-entries-fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

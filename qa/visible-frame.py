#!/usr/bin/env python3
"""Reject a blank QEMU PPM frame while retaining simple, reviewable metrics."""

from __future__ import annotations

import sys
from pathlib import Path


def inspect(path: Path) -> tuple[float, int, int]:
    with path.open("rb") as stream:
        if stream.readline().strip() != b"P6":
            raise ValueError("QEMU frame is not a binary PPM")

        def header_line() -> bytes:
            while True:
                line = stream.readline()
                if not line:
                    raise ValueError("incomplete PPM header")
                line = line.split(b"#", 1)[0].strip()
                if line:
                    return line

        dimensions = header_line().split()
        if len(dimensions) != 2:
            raise ValueError("invalid PPM dimensions")
        width, height = (int(value) for value in dimensions)
        if width <= 0 or height <= 0 or width * height > 100_000_000:
            raise ValueError("PPM dimensions out of range")
        if header_line() != b"255":
            raise ValueError("unsupported PPM color depth")
        pixels = stream.read()

    total = width * height
    if len(pixels) != total * 3:
        raise ValueError("PPM pixel data is incomplete")
    stride = max(1, total // 20_000)
    sampled = 0
    visible = 0
    colors: set[bytes] = set()
    for pixel in range(0, total, stride):
        color = pixels[pixel * 3:pixel * 3 + 3]
        sampled += 1
        if max(color) >= 40:
            visible += 1
        colors.add(color)
    return visible / sampled, sampled, len(colors)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: visible-frame.py <qemu-screendump.ppm>", file=sys.stderr)
        return 2
    try:
        fraction, sampled, colors = inspect(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        print(f"invalid_frame={exc}", file=sys.stderr)
        return 2
    print(f"visible_fraction={fraction:.4f} sampled_pixels={sampled} distinct_colors={colors}")
    return 0 if fraction >= 0.08 and colors >= 16 else 1


if __name__ == "__main__":
    raise SystemExit(main())

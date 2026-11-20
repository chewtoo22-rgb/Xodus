#!/usr/bin/env python3
"""Derive small bootloader/Plymouth PNGs from the approved Xodus video.

This is a maintainer tool, not part of the ISO build. Generated PNGs are
checked into Git so building the ISO needs neither ffmpeg nor Pillow.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageEnhance


HERE = Path(__file__).resolve().parent
BOOT = HERE.parent
MASTER = HERE / "xodus-boot-master.mp4"
ASSETS = BOOT / "assets"
PLYMOUTH = ASSETS / "plymouth"
EXPECTED_SHA256 = "1d114cddaba483c554d375a978b6474e57d20d70f88836903494c111c8ceb90b"
FRAME_COUNT = 241
FRAME_RATE = 24


def ffmpeg_executable() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise SystemExit("pass an ffmpeg executable or install imageio-ffmpeg") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(executable: str, *args: str) -> None:
    subprocess.run(
        [executable, "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
    )


def still(executable: str, seconds: float, destination: Path) -> None:
    run_ffmpeg(
        executable, "-ss", str(seconds), "-i", str(MASTER),
        "-frames:v", "1", "-update", "1", str(destination),
    )


def quantized_png(image: Image.Image, path: Path) -> None:
    image.convert("RGB").quantize(
        colors=256,
        method=Image.Quantize.FASTOCTREE,
        dither=Image.Dither.NONE,
    ).save(path, optimize=True)


def make_menu_background(source: Image.Image, wordmark: Image.Image, *,
                         include_wordmark: bool) -> Image.Image:
    # The selected X1 frame is kept recognizable at the right. The left and
    # middle stay near black so firmware menu entries retain contrast.
    canvas = Image.new("RGB", (1920, 1080), (2, 2, 8))
    subject = source.resize((1450, 816), Image.Resampling.LANCZOS)
    subject = ImageEnhance.Brightness(subject).enhance(0.42)
    canvas.paste(subject, (620, 144))
    shade = Image.new("RGB", canvas.size, (1, 1, 5))
    for x in range(1920):
        # Deliberately fade out the video on the text side of the menu.
        strength = max(0.0, 0.94 - (x / 1400.0))
        if strength <= 0:
            continue
        strip = shade.crop((x, 0, x + 1, 1080))
        base = canvas.crop((x, 0, x + 1, 1080))
        canvas.paste(Image.blend(base, strip, strength), (x, 0))
    if include_wordmark:
        word = wordmark.crop((255, 425, 1665, 655))
        word = word.resize((700, 114), Image.Resampling.LANCZOS)
        word = ImageEnhance.Brightness(word).enhance(1.8)
        canvas.paste(word, (126, 106))
    return canvas


def main() -> None:
    if not MASTER.is_file() or hashlib.sha256(MASTER.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise SystemExit("approved boot master is missing or changed")
    executable = ffmpeg_executable()
    PLYMOUTH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="xodus-boot-assets-") as temporary:
        temp = Path(temporary)
        run_ffmpeg(
            executable, "-i", str(MASTER), "-an", "-vf",
            f"fps={FRAME_RATE},scale=960:540:flags=lanczos", str(temp / "frame-%03d.png"),
        )
        sampled = sorted(temp.glob("frame-*.png"))
        if len(sampled) != FRAME_COUNT:
            raise SystemExit(f"expected {FRAME_COUNT} source-rate frames, got {len(sampled)}")
        # Plymouth/UEFI/GRUB accept RGB PNGs. Keep the violet gradients intact;
        # only the BIOS vesamenu background needs a 256-colour palette.
        for index, path in enumerate(sampled):
            with Image.open(path) as image:
                image.convert("RGB").save(PLYMOUTH / f"frame-{index:03d}.png", optimize=True)
        still(executable, 8.5, temp / "x1.png")
        still(executable, 4.5, temp / "wordmark.png")
        with Image.open(temp / "x1.png") as x1, Image.open(temp / "wordmark.png") as word:
            loader = make_menu_background(x1.convert("RGB"), word.convert("RGB"), include_wordmark=True)
            grub = make_menu_background(x1.convert("RGB"), word.convert("RGB"), include_wordmark=False)
            loader.save(ASSETS / "ploader-background.png", optimize=True)
            grub.save(ASSETS / "grub-background.png", optimize=True)
            bios = Image.new("RGB", (640, 480), (2, 2, 8))
            bios_subject = grub.resize((640, 360), Image.Resampling.LANCZOS)
            bios_subject = ImageEnhance.Brightness(bios_subject).enhance(0.5)
            bios.paste(bios_subject, (0, 60))
            quantized_png(bios, ASSETS / "syslinux-splash.png")
        with Image.open(temp / "x1.png") as x1:
            # The firmware tile references the same purple-lit X from the film.
            icon = x1.convert("RGB").crop((470, 275, 1450, 835))
            icon = icon.resize((128, 128), Image.Resampling.LANCZOS)
            icon.save(ASSETS / "os_xodus.png", optimize=True)
    # Remove only earlier generated samples in this tool's owned directory.
    expected = {f"frame-{index:03d}.png" for index in range(FRAME_COUNT)}
    for path in PLYMOUTH.glob("frame-*.png"):
        if path.name not in expected:
            path.unlink()
    total = sum(p.stat().st_size for p in ASSETS.rglob("*.png"))
    manifest = HERE / "assets.sha256"
    manifest.write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ASSETS).as_posix()}\n"
            for path in sorted(ASSETS.rglob("*.png"))
        ),
        encoding="ascii",
    )
    print(f"Derived {FRAME_COUNT} Plymouth frames at {FRAME_RATE} fps and firmware assets ({total} bytes)")


if __name__ == "__main__":
    main()

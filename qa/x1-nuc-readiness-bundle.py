#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import re
import sys
import tempfile

HEX40 = re.compile(r"^[0-9a-f]{40}$")
LIVE_FSTYPES = {"overlay", "squashfs", "erofs", "tmpfs", "rootfs"}
LIVE_SOURCE_PATTERNS = (
    re.compile(r"airootfs", re.I),
    re.compile(r"^/dev/loop"),
    re.compile(r"^/dev/mapper/ventoy", re.I),
)


def fail(message: str) -> None:
    raise ValueError(message)


def regular_file(path: pathlib.Path) -> None:
    if path.is_symlink():
        fail(f"symlink not allowed: {path}")
    if not path.is_file():
        fail(f"required file missing: {path}")


def parse_kv(path: pathlib.Path) -> dict[str, str]:
    regular_file(path)
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw:
            continue
        if "=" not in raw:
            fail(f"malformed key/value line in {path.name}")
        key, value = raw.split("=", 1)
        if not key or key in out:
            fail(f"duplicate/empty key in {path.name}: {key!r}")
        out[key] = value
    return out


def parse_json(path: pathlib.Path) -> dict:
    regular_file(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path.name}") from exc
    if not isinstance(value, dict):
        fail(f"top-level JSON object required in {path.name}")
    return value


def validate(hardware_summary: pathlib.Path, first_boot_json: pathlib.Path, candidate_sha: str) -> dict:
    if not HEX40.fullmatch(candidate_sha):
        fail("candidate SHA must be exactly 40 lowercase hexadecimal characters")

    hw = parse_kv(hardware_summary)
    fb = parse_json(first_boot_json)

    required_hw = {
        "captured_at_utc",
        "candidate_sha",
        "upstream_sha",
        "hostname",
        "kernel",
        "root_source",
        "root_fstype",
        "boot_mode",
        "root_backing_disk",
        "collector",
        "physical_install_claim",
    }
    missing_hw = sorted(required_hw - set(hw))
    if missing_hw:
        fail(f"installed-hardware summary missing keys: {missing_hw}")
    if not HEX40.fullmatch(hw["candidate_sha"]):
        fail("installed-hardware candidate SHA is malformed")
    if hw["candidate_sha"] != candidate_sha:
        fail("installed-hardware evidence does not match requested candidate")
    if not HEX40.fullmatch(hw["upstream_sha"]):
        fail("installed-hardware upstream SHA is malformed")
    if hw["collector"] != "pass":
        fail("installed-hardware collector did not pass")
    if hw["boot_mode"].lower() != "uefi":
        fail("X1 NUC readiness requires UEFI installed boot")
    if hw["physical_install_claim"] != "not_automatic":
        fail("installed-hardware evidence claim guard missing")

    root_source = hw["root_source"]
    root_fstype = hw["root_fstype"].lower()
    if not root_source:
        fail("installed root source is empty")
    if root_fstype in LIVE_FSTYPES:
        fail("live/ephemeral root filesystem rejected")
    if any(pattern.search(root_source) for pattern in LIVE_SOURCE_PATTERNS):
        fail("live root source rejected")

    required_fb = {
        "schema",
        "status",
        "first_boot_completed_utc",
        "firmware",
        "root_source",
        "root_fstype",
        "ai_tier",
        "ai_backend",
        "hardware_validation_claim",
    }
    if set(fb) != required_fb:
        fail("unexpected first-boot acceptance schema")
    if fb["schema"] != 1 or fb["status"] != "pass":
        fail("first-boot runtime acceptance did not pass")
    if fb["firmware"] != "uefi":
        fail("first-boot acceptance is not UEFI")
    if fb["hardware_validation_claim"] is not False:
        fail("first-boot acceptance must not claim hardware validation")
    if fb["root_source"] != root_source:
        fail("hardware evidence and first-boot acceptance root sources disagree")
    if str(fb["root_fstype"]).lower() != root_fstype:
        fail("hardware evidence and first-boot acceptance root filesystems disagree")

    return {
        "schema": 1,
        "status": "ready_for_nuc_hardware_test",
        "candidate_sha": candidate_sha,
        "upstream_sha": hw["upstream_sha"],
        "boot_mode": "uefi",
        "root_source": root_source,
        "root_fstype": root_fstype,
        "root_backing_disk": hw["root_backing_disk"],
        "first_boot_completed_utc": fb["first_boot_completed_utc"],
        "ai_tier": fb["ai_tier"],
        "ai_backend": fb["ai_backend"],
        "physical_install_claim": "not_automatic",
        "hardware_validation_claim": False,
    }


def atomic_write(path: pathlib.Path, content: str) -> None:
    if path.is_symlink():
        fail("output symlink not allowed")
    if path.exists() and not path.is_file():
        fail("output must be a regular file")

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    cursor = parent
    while True:
        if cursor.is_symlink():
            fail(f"symlinked output parent not allowed: {cursor}")
        if not cursor.is_dir():
            fail(f"output parent is not a directory: {cursor}")
        if cursor == cursor.parent:
            break
        cursor = cursor.parent

    fd = -1
    tmp_name = ""
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            text=True,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        tmp_name = ""
        dir_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a coherent Xodus X1 NUC readiness evidence bundle")
    parser.add_argument("--hardware-summary", required=True)
    parser.add_argument("--first-boot-json", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        result = validate(
            pathlib.Path(args.hardware_summary),
            pathlib.Path(args.first_boot_json),
            args.candidate_sha,
        )
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output:
            atomic_write(pathlib.Path(args.output), encoded)
    except (OSError, ValueError) as exc:
        print(f"xodus-x1-nuc-readiness-bundle: FAIL: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LIVE_ROOT_TOKENS = ("overlay", "airootfs", "squashfs", "tmpfs", "rootfs")


def read_summary(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"summary is not a regular file: {path}")
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#"):
            continue
        if "=" not in raw:
            raise ValueError(f"malformed summary line in {path}: {raw!r}")
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in data:
            raise ValueError(f"invalid or duplicate key in {path}: {key!r}")
        data[key] = value
    return data


def check_candidate(summary: dict[str, str], expected: str, label: str, blockers: list[str]) -> None:
    recorded = summary.get("candidate_sha", "")
    if not recorded:
        blockers.append(f"{label}_candidate_sha_missing")
    elif not SHA_RE.fullmatch(recorded):
        blockers.append(f"{label}_candidate_sha_invalid")
    elif recorded != expected:
        blockers.append(f"{label}_candidate_sha_mismatch")


def evaluate(candidate_sha: str, live: dict[str, str], installed: dict[str, str]) -> dict[str, object]:
    blockers: list[str] = []
    candidate_valid = bool(SHA_RE.fullmatch(candidate_sha))
    if not candidate_valid:
        blockers.append("candidate_sha_invalid")

    if live.get("collector") != "pass":
        blockers.append("live_collector_not_pass")
    if installed.get("collector") != "pass":
        blockers.append("installed_collector_not_pass")
    if installed.get("boot_mode") != "uefi":
        blockers.append("installed_boot_not_uefi")
    if installed.get("physical_install_claim") != "not_automatic":
        blockers.append("unsafe_physical_install_claim")

    root_source = installed.get("root_source", "")
    root_fstype = installed.get("root_fstype", "")
    root_identity = f"{root_source}:{root_fstype}".lower()
    if not root_source or not root_fstype:
        blockers.append("installed_root_identity_missing")
    elif any(token in root_identity for token in LIVE_ROOT_TOKENS):
        blockers.append("installed_root_looks_live")

    if installed.get("root_backing_disk", "").lower() in ("", "unknown"):
        blockers.append("installed_backing_disk_missing")

    upstream_sha = installed.get("upstream_sha", "")
    if not upstream_sha:
        blockers.append("installed_upstream_sha_missing")
    elif not SHA_RE.fullmatch(upstream_sha):
        blockers.append("installed_upstream_sha_invalid")

    if candidate_valid:
        check_candidate(live, candidate_sha, "live", blockers)
        check_candidate(installed, candidate_sha, "installed", blockers)

    blockers = sorted(set(blockers))
    return {
        "schema": 1,
        "candidate_sha": candidate_sha,
        "upstream_sha": upstream_sha if SHA_RE.fullmatch(upstream_sha) else "",
        "evidence_ready_for_operator_review": not blockers,
        "hardware_validation_claim": False,
        "blockers": blockers,
    }


def publish_output(path: Path, payload: str) -> None:
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError(f"output parent is not a safe directory: {parent}")
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing output: {path}")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_path, path)
        temp_path = None
        dir_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed acceptance gate for X1 NUC evidence summaries")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--live-summary", required=True, type=Path)
    parser.add_argument("--installed-summary", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        result = evaluate(args.candidate_sha, read_summary(args.live_summary), read_summary(args.installed_summary))
    except (OSError, UnicodeError, ValueError) as exc:
        result = {
            "schema": 1,
            "candidate_sha": args.candidate_sha,
            "upstream_sha": "",
            "evidence_ready_for_operator_review": False,
            "hardware_validation_claim": False,
            "blockers": [f"input_error:{type(exc).__name__}"],
        }

    payload = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        try:
            publish_output(args.output, payload)
        except (OSError, ValueError) as exc:
            print(f"refusing unsafe output: {exc}", file=sys.stderr)
            return 3
    sys.stdout.write(payload)
    return 0 if result["evidence_ready_for_operator_review"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

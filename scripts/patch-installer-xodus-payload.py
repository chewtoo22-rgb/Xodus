#!/usr/bin/env python3
"""Inject release-critical Xodus payload bytes into an audited pearOS setup.

The upstream installer builds /mnt from packages instead of cloning the live
airootfs. Therefore the installed Xodus first-boot payload and build identity
must not depend on files already existing inside whatever live ISO happened to
boot the installer. Qualification embeds exact reviewed bytes, verifies their
hashes after reconstruction, installs them into /mnt, and enables first boot.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit(f"usage: {sys.argv[0]} <installer-setup> <output>")

src = Path(sys.argv[1])
out = Path(sys.argv[2])
text = src.read_text()
repo_root = Path(__file__).resolve().parents[1]

marker = "  # Sends the install finished messages to the frontend\n"
if text.count(marker) != 1:
    raise SystemExit("installer completion contract changed; refusing Xodus payload injection")

sha_re = re.compile(r"^[0-9a-f]{40}$")
source_sha = os.environ.get("GITHUB_HEAD_SHA", "")
if not source_sha:
    source_sha = subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
    ).strip()
if not sha_re.fullmatch(source_sha):
    raise SystemExit("qualification source commit is not an exact lowercase SHA")

lock_rows = [
    line for line in (repo_root / "upstream/iso.lock").read_text().splitlines()
    if line and not line.startswith("#")
]
if len(lock_rows) != 1:
    raise SystemExit("ISO provenance lock must contain exactly one active row")
lock_parts = lock_rows[0].split("|")
if len(lock_parts) != 4 or not sha_re.fullmatch(lock_parts[2]):
    raise SystemExit("ISO provenance lock has invalid upstream commit")
upstream_sha = lock_parts[2]
build_info = (
    f"XODUS_SOURCE_COMMIT={source_sha}\n"
    f"XODUS_UPSTREAM_COMMIT={upstream_sha}\n"
).encode()

payloads = [
    ((repo_root / "overlay/first-boot/xodus-first-boot").read_bytes(), "/usr/lib/xodus/xodus-first-boot", 0o755),
    ((repo_root / "overlay/first-boot/xodus-first-boot.service").read_bytes(), "/usr/lib/systemd/system/xodus-first-boot.service", 0o644),
    ((repo_root / "overlay/first-boot/xodus-ai-first-boot").read_bytes(), "/usr/lib/xodus/xodus-ai-first-boot", 0o755),
    ((repo_root / "overlay/first-boot/xodus-ai-first-boot.service").read_bytes(), "/usr/lib/systemd/system/xodus-ai-first-boot.service", 0o644),
    ((repo_root / "scripts/xodus-ai-select.py").read_bytes(), "/usr/lib/xodus/xodus-ai-select.py", 0o755),
    (build_info, "/usr/lib/xodus/build-info", 0o644),
]

lines = [
    "  # Xodus installed-system payload is embedded from the exact qualification checkout.",
    "  # Do not depend on the booted live ISO already containing these files.",
    "  xodus_payload_tmp=$(mktemp -d)",
    "  trap 'rm -rf \"$xodus_payload_tmp\"' RETURN",
]

manifest: list[str] = []
for index, (raw, destination, mode) in enumerate(payloads):
    encoded = base64.b64encode(raw).decode("ascii")
    digest = hashlib.sha256(raw).hexdigest()
    tmp = f"$xodus_payload_tmp/payload-{index}"
    q_dest = shlex.quote(destination)
    lines.extend([
        f"  printf '%s' '{encoded}' | base64 -d > \"{tmp}\" \\",
        f"    || error_exit \"Failed to decode embedded Xodus payload: {destination}\"",
        f"  printf '%s  %s\\n' '{digest}' \"{tmp}\" | sha256sum -c - >/dev/null 2>&1 \\",
        f"    || error_exit \"Embedded Xodus payload hash mismatch: {destination}\"",
        f"  install -D -m {mode:04o} \"{tmp}\" /mnt{q_dest} \\",
        f"    || error_exit \"Failed to install embedded Xodus payload: {destination}\"",
    ])
    manifest.append(f"{destination}:{mode:04o}:{digest}")

lines.extend([
    "  rm -rf \"$xodus_payload_tmp\"",
    "  trap - RETURN",
    "  install -d -m 0755 /mnt/var/lib/xodus/first-boot /mnt/var/lib/xodus/ai \\",
    "    /mnt/etc/systemd/system/multi-user.target.wants",
    "  ln -sfn /usr/lib/systemd/system/xodus-first-boot.service \\",
    "    /mnt/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service",
    "  ln -sfn /usr/lib/systemd/system/xodus-ai-first-boot.service \\",
    "    /mnt/etc/systemd/system/multi-user.target.wants/xodus-ai-first-boot.service",
    "  test ! -e /mnt/var/lib/xodus/first-boot/complete \\",
    "    || error_exit \"Installed image unexpectedly pre-marked first boot complete\"",
    "  test -x /mnt/usr/lib/xodus/xodus-first-boot \\",
    "    || error_exit \"Installed Xodus first-boot runner verification failed\"",
    "  test -x /mnt/usr/lib/xodus/xodus-ai-first-boot \\",
    "    || error_exit \"Installed Xodus AI first-boot runner verification failed\"",
    "  test -x /mnt/usr/lib/xodus/xodus-ai-select.py \\",
    "    || error_exit \"Installed Xodus AI selector verification failed\"",
    f"  grep -Fqx 'XODUS_SOURCE_COMMIT={source_sha}' /mnt/usr/lib/xodus/build-info \\",
    "    || error_exit \"Installed Xodus source provenance verification failed\"",
    f"  grep -Fqx 'XODUS_UPSTREAM_COMMIT={upstream_sha}' /mnt/usr/lib/xodus/build-info \\",
    "    || error_exit \"Installed Xodus upstream provenance verification failed\"",
    "  test -L /mnt/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service \\",
    "    || error_exit \"Installed Xodus first-boot service enablement failed\"",
    "  test -L /mnt/etc/systemd/system/multi-user.target.wants/xodus-ai-first-boot.service \\",
    "    || error_exit \"Installed Xodus AI first-boot service enablement failed\"",
    "  echo \"Installed Xodus first-boot/AI payload and build provenance from qualification checkout\" >> /home/liveuser/Desktop/install.log",
    "",
])

handoff = "\n".join(lines)
patched = text.replace(marker, handoff + marker, 1)
out.write_text(patched)
out.chmod(0o700)
print(f"input_sha256={hashlib.sha256(text.encode()).hexdigest()}")
print(f"output_sha256={hashlib.sha256(patched.encode()).hexdigest()}")
print("xodus_payload_handoff=embedded-qualified-bytes-first-boot-ai-first-boot-build-provenance-fail-closed")
print(f"xodus_source_commit={source_sha}")
print(f"xodus_upstream_commit={upstream_sha}")
for entry in manifest:
    print("xodus_payload=" + entry)

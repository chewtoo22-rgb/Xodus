#!/usr/bin/env python3
"""Inject release-critical Xodus payload bytes into an audited pearOS setup.

The upstream installer builds /mnt from packages instead of cloning the live
a irootfs. Therefore the installed Xodus first-boot payload must not depend on
those files already existing inside whatever live ISO happened to boot the
installer. Qualification embeds the exact reviewed repository payload bytes in
the generated installer, verifies their hashes after reconstruction, installs
them into /mnt, and then enables the first-boot services. The transform remains
narrow and fails closed if the pinned upstream completion boundary or payload
set changes.
"""
from __future__ import annotations

import base64
import hashlib
import shlex
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

payloads = (
    (repo_root / "overlay/first-boot/xodus-first-boot", "/usr/lib/xodus/xodus-first-boot", 0o755),
    (repo_root / "overlay/first-boot/xodus-first-boot.service", "/usr/lib/systemd/system/xodus-first-boot.service", 0o644),
    (repo_root / "overlay/first-boot/xodus-ai-first-boot", "/usr/lib/xodus/xodus-ai-first-boot", 0o755),
    (repo_root / "overlay/first-boot/xodus-ai-first-boot.service", "/usr/lib/systemd/system/xodus-ai-first-boot.service", 0o644),
    (repo_root / "scripts/xodus-ai-select.py", "/usr/lib/xodus/xodus-ai-select.py", 0o755),
)

missing = [str(path) for path, _, _ in payloads if not path.is_file()]
if missing:
    raise SystemExit("required Xodus payload missing from qualification checkout: " + ", ".join(missing))

lines = [
    "  # Xodus installed-system payload is embedded from the exact qualification checkout.",
    "  # Do not depend on the booted live ISO already containing these files.",
    "  xodus_payload_tmp=$(mktemp -d)",
    "  trap 'rm -rf \"$xodus_payload_tmp\"' RETURN",
]

manifest: list[str] = []
for index, (source, destination, mode) in enumerate(payloads):
    raw = source.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    digest = hashlib.sha256(raw).hexdigest()
    tmp = f"$xodus_payload_tmp/payload-{index}"
    q_dest = shlex.quote(destination)
    lines.extend(
        [
            f"  printf '%s' '{encoded}' | base64 -d > \"{tmp}\" \\",
            f"    || error_exit \"Failed to decode embedded Xodus payload: {destination}\"",
            f"  printf '%s  %s\\n' '{digest}' \"{tmp}\" | sha256sum -c - >/dev/null 2>&1 \\",
            f"    || error_exit \"Embedded Xodus payload hash mismatch: {destination}\"",
            f"  install -D -m {mode:04o} \"{tmp}\" /mnt{q_dest} \\",
            f"    || error_exit \"Failed to install embedded Xodus payload: {destination}\"",
        ]
    )
    manifest.append(f"{destination}:{mode:04o}:{digest}")

lines.extend(
    [
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
        "  test -L /mnt/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service \\",
        "    || error_exit \"Installed Xodus first-boot service enablement failed\"",
        "  test -L /mnt/etc/systemd/system/multi-user.target.wants/xodus-ai-first-boot.service \\",
        "    || error_exit \"Installed Xodus AI first-boot service enablement failed\"",
        "  echo \"Installed Xodus first-boot/AI payload from qualification checkout\" >> /home/liveuser/Desktop/install.log",
        "",
    ]
)

handoff = "\n".join(lines)
patched = text.replace(marker, handoff + marker, 1)
out.write_text(patched)
out.chmod(0o700)
print(f"input_sha256={hashlib.sha256(text.encode()).hexdigest()}")
print(f"output_sha256={hashlib.sha256(patched.encode()).hexdigest()}")
print("xodus_payload_handoff=embedded-qualified-bytes-first-boot-ai-first-boot-fail-closed")
for entry in manifest:
    print("xodus_payload=" + entry)

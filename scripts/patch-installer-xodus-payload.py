#!/usr/bin/env python3
"""Inject the Xodus installed-system payload handoff into an audited pearOS setup.

The pearOS installer builds /mnt from packages rather than cloning the live
airootfs, so Xodus-only files present on the qualified ISO must be copied into
the installed root explicitly. This transform is intentionally narrow and
fails closed if the pinned upstream completion boundary changes.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit(f"usage: {sys.argv[0]} <installer-setup> <output>")

src = Path(sys.argv[1])
out = Path(sys.argv[2])
text = src.read_text()

marker = "  # Sends the install finished messages to the frontend\n"
if text.count(marker) != 1:
    raise SystemExit("installer completion contract changed; refusing Xodus payload injection")

handoff = r'''  # Xodus is layered into the live airootfs, while the upstream installer
  # constructs /mnt from packages. Preserve the release-critical Xodus-only
  # first-boot payload explicitly before declaring installation complete.
  xodus_payload=(
    /usr/lib/xodus/xodus-first-boot
    /usr/lib/systemd/system/xodus-first-boot.service
    /usr/lib/xodus/xodus-ai-first-boot
    /usr/lib/systemd/system/xodus-ai-first-boot.service
  )
  for source_path in "${xodus_payload[@]}"; do
    test -f "$source_path" || error_exit "Required Xodus installed payload missing from live image: $source_path"
    install -D -m "$(stat -c '%a' "$source_path")" "$source_path" "/mnt$source_path" \
      || error_exit "Failed to install Xodus payload: $source_path"
  done
  if test -x /usr/lib/xodus/xodus-ai-select.py; then
    install -D -m 0755 /usr/lib/xodus/xodus-ai-select.py /mnt/usr/lib/xodus/xodus-ai-select.py \
      || error_exit "Failed to install Xodus AI selector"
  fi
  install -d -m 0755 /mnt/var/lib/xodus/first-boot /mnt/var/lib/xodus/ai \
    /mnt/etc/systemd/system/multi-user.target.wants
  ln -sfn /usr/lib/systemd/system/xodus-first-boot.service \
    /mnt/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service
  ln -sfn /usr/lib/systemd/system/xodus-ai-first-boot.service \
    /mnt/etc/systemd/system/multi-user.target.wants/xodus-ai-first-boot.service
  test ! -e /mnt/var/lib/xodus/first-boot/complete \
    || error_exit "Installed image unexpectedly pre-marked first boot complete"
  test -x /mnt/usr/lib/xodus/xodus-first-boot \
    || error_exit "Installed Xodus first-boot runner verification failed"
  test -L /mnt/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service \
    || error_exit "Installed Xodus first-boot service enablement failed"
  echo "Installed Xodus first-boot payload from qualified live image" >> /home/liveuser/Desktop/install.log

'''

patched = text.replace(marker, handoff + marker, 1)
out.write_text(patched)
out.chmod(0o700)
print(f"input_sha256={hashlib.sha256(text.encode()).hexdigest()}")
print(f"output_sha256={hashlib.sha256(patched.encode()).hexdigest()}")
print("xodus_payload_handoff=first-boot-ai-first-boot-fail-closed")

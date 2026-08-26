#!/usr/bin/env python3
"""Deterministically harden the pinned pearOS installer package phase.

The upstream installer records individual pacstrap failures but continues into
service enablement. That turns a package/mirror failure into a misleading later
error (for example missing sddm/plasma-desktop). Xodus verifies the pinned
upstream blob first, then applies this narrowly-scoped runtime transform for the
destructive VM proof.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit(f"usage: {sys.argv[0]} <audited-upstream-setup> <output>")

src = Path(sys.argv[1])
out = Path(sys.argv[2])
text = src.read_text()

old = '''  trap - ERR
  failed_packages=0
  total_packages=${#BASE_PACKAGES[@]}
  installed_packages=0
  
  # Progress calculation: 18% to 70% for package installation (52% range for all packages)
  for package in "${BASE_PACKAGES[@]}"; do
    if ! pacstrap /mnt "$package" 2>/dev/null; then
      echo "Warning: Failed to install $package" >> /home/liveuser/Desktop/install.log
      echo "FAILED: $package" >> /tmp/failed_packages.log
      ((failed_packages++))
    else
      ((installed_packages++))
    fi
    
    # Update progress: 18% + (installed_packages / total_packages) * 52%
    progress=$((18 + (installed_packages * 52 / total_packages)))
    update_progress "$progress"
  done
  
  trap 'line_no=$LINENO; error_line=$(sed -n "${line_no}p" "${BASH_SOURCE[0]}" | sed "s/^[[:space:]]*//"); error_exit "Unexpected error at line $line_no:\\n\\n    $error_line"' ERR
  
  echo "Installed: $installed_packages/$total_packages packages" >> /home/liveuser/Desktop/install.log
  
  update_progress "70"
'''

new = '''  trap - ERR
  failed_packages=0
  total_packages=${#BASE_PACKAGES[@]}
  installed_packages=0
  failed_package_names=()
  : > /tmp/failed_packages.log
  
  # Progress calculation: 18% to 70% for package installation (52% range for all packages)
  for package in "${BASE_PACKAGES[@]}"; do
    if ! pacstrap /mnt "$package" 2>>/home/liveuser/Desktop/install.log; then
      echo "Warning: Failed first install attempt for $package" >> /home/liveuser/Desktop/install.log
      failed_package_names+=("$package")
      ((failed_packages++))
    else
      ((installed_packages++))
    fi
    
    # Update progress: 18% + (installed_packages / total_packages) * 52%
    progress=$((18 + (installed_packages * 52 / total_packages)))
    update_progress "$progress"
  done

  # A moving Arch repository or transient mirror failure can make a single
  # pacstrap invocation fail while later requests succeed. Refresh once and
  # retry only the packages that failed. Never continue into service setup if
  # any required package is still absent.
  if (( failed_packages > 0 )); then
    echo "Retrying $failed_packages failed package(s) after database refresh" >> /home/liveuser/Desktop/install.log
    pacman -Syy --noconfirm >> /home/liveuser/Desktop/install.log 2>&1 || true
    retry_failures=()
    for package in "${failed_package_names[@]}"; do
      if pacstrap /mnt "$package" >> /home/liveuser/Desktop/install.log 2>&1; then
        echo "Recovered package on retry: $package" >> /home/liveuser/Desktop/install.log
        ((installed_packages++))
      else
        echo "FAILED: $package" >> /tmp/failed_packages.log
        retry_failures+=("$package")
      fi
    done
    failed_package_names=("${retry_failures[@]}")
    failed_packages=${#failed_package_names[@]}
  fi

  trap 'line_no=$LINENO; error_line=$(sed -n "${line_no}p" "${BASH_SOURCE[0]}" | sed "s/^[[:space:]]*//"); error_exit "Unexpected error at line $line_no:\\n\\n    $error_line"' ERR

  echo "Installed: $installed_packages/$total_packages packages" >> /home/liveuser/Desktop/install.log
  if (( failed_packages > 0 )); then
    error_exit "Required package installation failed after retry: ${failed_package_names[*]}"
  fi

  # Explicitly require the display-manager payload before service enablement.
  arch-chroot /mnt test -x /usr/bin/sddm || error_exit "Required SDDM binary missing after package phase"
  arch-chroot /mnt test -d /usr/share/plasma || error_exit "Required Plasma payload missing after package phase"
  
  update_progress "70"
'''

count = text.count(old)
if count != 1:
    raise SystemExit(
        f"upstream package-install contract changed: expected one patch target, found {count}"
    )

patched = text.replace(old, new, 1)
out.write_text(patched)
out.chmod(0o700)

src_sha = hashlib.sha256(text.encode()).hexdigest()
out_sha = hashlib.sha256(patched.encode()).hexdigest()
print(f"upstream_setup_sha256={src_sha}")
print(f"xodus_setup_sha256={out_sha}")
print("package_retry_policy=one-refresh-one-retry-then-fail-closed")

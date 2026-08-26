#!/usr/bin/env python3
"""Deterministically harden the pinned pearOS installer package phase.

The pinned upstream package list is currently internally inconsistent on a
fresh 2026 Arch root: some entries conflict with packages/files installed by
earlier entries. Xodus audits the exact upstream installer blob first, then
applies this bounded runtime transform only for the destructive VM proof.

Observed conflict repairs are explicit and fail closed:
- chwd supersedes the mutually-exclusive chwd-db entry while preserving the
  later chwd --autoconfigure contract.
- lsb-release/open-vm-tools may replace the /etc/lsb-release file shipped by
  filesystem. After the exact-path overwrite, ownership of that one path is
  transferred in pacman's local metadata from filesystem to lsb-release.
- pipewire-jack replaces the mutually-exclusive jack2 implementation.
- plasma-desktop may replace the single lockscreen QML path already staged by
  the pearOS payload.

Anything outside those observed cases still gets one database refresh and one
normal retry, then aborts with exact package names.
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
    
    progress=$((18 + (installed_packages * 52 / total_packages)))
    update_progress "$progress"
  done

  # A moving repository can cause transient failures, but the pinned pearOS
  # package list also contains several deterministic conflict pairs. Repair only
  # those conflicts observed in retained CI evidence, then perform one ordinary
  # retry for anything else.
  if (( failed_packages > 0 )); then
    echo "Repairing/retrying $failed_packages failed package(s) after database refresh" >> /home/liveuser/Desktop/install.log
    pacman -Syy --noconfirm >> /home/liveuser/Desktop/install.log 2>&1 || true
    retry_failures=()

    for package in "${failed_package_names[@]}"; do
      recovered=false
      case "$package" in
        chwd-db)
          # Current chwd and chwd-db packages conflict. The installer later
          # executes `chwd --autoconfigure`, so keep the working chwd package and
          # treat the stale duplicate database package as superseded.
          if arch-chroot /mnt pacman -Q chwd >> /home/liveuser/Desktop/install.log 2>&1 \
             && arch-chroot /mnt test -x /usr/bin/chwd; then
            echo "Superseded conflicting package chwd-db with installed chwd" >> /home/liveuser/Desktop/install.log
            recovered=true
          fi
          ;;
        lsb-release|open-vm-tools)
          # filesystem currently owns /etc/lsb-release, while open-vm-tools
          # requires the lsb-release package. First accept an already-clean
          # repair so this case is idempotent when both package-list entries
          # failed on the first pass.
          if arch-chroot /mnt pacman -Q lsb-release open-vm-tools \
               >> /home/liveuser/Desktop/install.log 2>&1 \
             && arch-chroot /mnt pacman -Qo /etc/lsb-release \
               >> /home/liveuser/Desktop/install.log 2>&1 \
             && arch-chroot /mnt pacman -Dk \
               >> /home/liveuser/Desktop/install.log 2>&1; then
            echo "Verified repaired package group: lsb-release/open-vm-tools" >> /home/liveuser/Desktop/install.log
            recovered=true
          else
            # Install the two packages atomically while allowing replacement of
            # only the observed path. pacman's --overwrite changes the payload
            # but leaves the old filesystem package ownership record in place,
            # so transfer ownership of exactly etc/lsb-release in the local DB.
            if arch-chroot /mnt pacman -S --noconfirm \
                 --overwrite 'etc/lsb-release' lsb-release open-vm-tools \
                 >> /home/liveuser/Desktop/install.log 2>&1 \
               && arch-chroot /mnt pacman -Q lsb-release open-vm-tools \
                 >> /home/liveuser/Desktop/install.log 2>&1; then
              mapfile -t filesystem_files < <(find /mnt/var/lib/pacman/local -maxdepth 2 \
                -path '*/filesystem-*/files' -type f -print)
              mapfile -t lsb_files < <(find /mnt/var/lib/pacman/local -maxdepth 2 \
                -path '*/lsb-release-*/files' -type f -print)
              if (( ${#filesystem_files[@]} != 1 || ${#lsb_files[@]} != 1 )); then
                echo "ERROR: unexpected pacman local DB layout for lsb-release ownership repair" \
                  >> /home/liveuser/Desktop/install.log
              elif ! grep -Fxq 'etc/lsb-release' "${lsb_files[0]}"; then
                echo "ERROR: lsb-release package DB does not own expected etc/lsb-release path" \
                  >> /home/liveuser/Desktop/install.log
              else
                if grep -Fxq 'etc/lsb-release' "${filesystem_files[0]}"; then
                  db_tmp=$(mktemp)
                  awk '$0 != "etc/lsb-release"' "${filesystem_files[0]}" > "$db_tmp"
                  install -m 644 "$db_tmp" "${filesystem_files[0]}"
                  rm -f "$db_tmp"
                  echo "Transferred etc/lsb-release ownership metadata from filesystem to lsb-release" \
                    >> /home/liveuser/Desktop/install.log
                fi
                if arch-chroot /mnt pacman -Qo /etc/lsb-release \
                     >> /home/liveuser/Desktop/install.log 2>&1 \
                   && arch-chroot /mnt pacman -Dk \
                     >> /home/liveuser/Desktop/install.log 2>&1; then
                  echo "Recovered package conflict group: lsb-release/open-vm-tools" >> /home/liveuser/Desktop/install.log
                  recovered=true
                fi
              fi
            fi
          fi
          ;;
        pipewire-jack)
          # pipewire-jack and jack2 are mutually exclusive JACK providers. Drop
          # jack2 without dependency enforcement only within this atomic repair,
          # immediately install pipewire-jack, then require pacman's dependency
          # database check to be clean.
          arch-chroot /mnt pacman -Rdd --noconfirm jack2 \
            >> /home/liveuser/Desktop/install.log 2>&1 || true
          if arch-chroot /mnt pacman -S --noconfirm pipewire-jack \
               >> /home/liveuser/Desktop/install.log 2>&1 \
             && arch-chroot /mnt pacman -Q pipewire-jack \
               >> /home/liveuser/Desktop/install.log 2>&1 \
             && arch-chroot /mnt pacman -Dk \
               >> /home/liveuser/Desktop/install.log 2>&1; then
            echo "Recovered JACK provider conflict with pipewire-jack" >> /home/liveuser/Desktop/install.log
            recovered=true
          fi
          ;;
        plasma-desktop)
          # The pearOS payload stages one customized lockscreen QML file before
          # plasma-desktop. Permit replacement of only that known path.
          if arch-chroot /mnt pacman -S --noconfirm \
               --overwrite 'usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml' \
               plasma-desktop >> /home/liveuser/Desktop/install.log 2>&1 \
             && arch-chroot /mnt pacman -Q plasma-desktop \
               >> /home/liveuser/Desktop/install.log 2>&1; then
            echo "Recovered plasma-desktop staged-file conflict" >> /home/liveuser/Desktop/install.log
            recovered=true
          fi
          ;;
      esac

      if ! $recovered; then
        if pacstrap /mnt "$package" >> /home/liveuser/Desktop/install.log 2>&1; then
          echo "Recovered package on normal retry: $package" >> /home/liveuser/Desktop/install.log
          recovered=true
        fi
      fi

      if $recovered; then
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

  echo "Installed/satisfied: $installed_packages/$total_packages package entries" >> /home/liveuser/Desktop/install.log
  if (( failed_packages > 0 )); then
    error_exit "Required package installation failed after bounded conflict repair: ${failed_package_names[*]}"
  fi

  # Fail closed on the payloads needed by later installer steps.
  arch-chroot /mnt test -x /usr/bin/chwd || error_exit "Required chwd binary missing after package phase"
  arch-chroot /mnt test -x /usr/bin/sddm || error_exit "Required SDDM binary missing after package phase"
  arch-chroot /mnt test -d /usr/share/plasma || error_exit "Required Plasma payload missing after package phase"
  arch-chroot /mnt pacman -Q open-vm-tools pipewire-jack plasma-desktop \
    >> /home/liveuser/Desktop/install.log 2>&1 \
    || error_exit "Required repaired package group missing after package phase"
  arch-chroot /mnt pacman -Dk >> /home/liveuser/Desktop/install.log 2>&1 \
    || error_exit "Pacman dependency database inconsistent after conflict repair"
  
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
print("package_retry_policy=observed-conflict-repair-one-retry-then-fail-closed")

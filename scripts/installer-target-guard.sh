#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: installer-target-guard.sh /dev/DEVICE

Read-only preflight for the destructive Xodus/pearOS installer path.
The guard does not install anything; it only approves or rejects a whole-disk
installer target.

Disposable loop-device approval requires:
  XODUS_DISPOSABLE=1
  XODUS_INSTALL_CONFIRM=<exact device path>

Physical-disk approval is intentionally harder and requires BOTH:
  XODUS_ALLOW_PHYSICAL_INSTALL=YES-I-UNDERSTAND
  XODUS_INSTALL_CONFIRM=<exact device path>

Physical installation remains project-policy locked until the automated
post-install UEFI boot gate is implemented and green.
EOF
}

[[ $# -eq 1 ]] || { usage >&2; exit 64; }

candidate="$1"
[[ -b "$candidate" ]] || { echo "REFUSE: not a block device: $candidate" >&2; exit 2; }

target="$(readlink -f "$candidate")"
type="$(lsblk -ndo TYPE "$target" 2>/dev/null || true)"
[[ "$type" == "disk" || "$type" == "loop" ]] || {
  echo "REFUSE: installer target must be a whole disk/loop device, got type '$type': $target" >&2
  exit 3
}

# Never accept a device that is mounted itself or has mounted descendants.
if lsblk -nrpo NAME,MOUNTPOINT "$target" | awk 'NF >= 2 && $2 != "" { found=1 } END { exit !found }'; then
  echo "REFUSE: target or one of its descendants is mounted: $target" >&2
  lsblk -o NAME,TYPE,SIZE,MOUNTPOINTS "$target" >&2 || true
  exit 4
fi

# Resolve the device that backs the currently running root filesystem and
# refuse it even if it happens to be unmounted in a namespace edge case.
root_source="$(findmnt -nro SOURCE / 2>/dev/null || true)"
if [[ -n "$root_source" && -b "$root_source" ]]; then
  root_real="$(readlink -f "$root_source")"
  root_parent="$(lsblk -ndo PKNAME "$root_real" 2>/dev/null || true)"
  if [[ -n "$root_parent" ]]; then
    root_disk="$(readlink -f "/dev/$root_parent")"
  else
    root_disk="$root_real"
  fi
  if [[ "$target" == "$root_disk" || "$target" == "$root_real" ]]; then
    echo "REFUSE: target backs the running root filesystem: $target" >&2
    exit 5
  fi
fi

size_bytes="$(lsblk -bdno SIZE "$target" 2>/dev/null || echo 0)"
min_bytes=$((20 * 1024 * 1024 * 1024))
if (( size_bytes < min_bytes )); then
  echo "REFUSE: target is smaller than 20 GiB: $target ($size_bytes bytes)" >&2
  exit 6
fi

confirm="${XODUS_INSTALL_CONFIRM:-}"
[[ "$confirm" == "$target" || "$confirm" == "$candidate" ]] || {
  echo "REFUSE: exact-device confirmation missing. Set XODUS_INSTALL_CONFIRM=$target" >&2
  exit 7
}

if [[ "$type" == "loop" ]]; then
  [[ "${XODUS_DISPOSABLE:-0}" == "1" ]] || {
    echo "REFUSE: loop target is not marked disposable (XODUS_DISPOSABLE=1 required)" >&2
    exit 8
  }

  backing="$(losetup -nO BACK-FILE "$target" 2>/dev/null | head -n1 || true)"
  [[ -n "$backing" ]] || {
    echo "REFUSE: disposable loop device has no resolvable backing file: $target" >&2
    exit 9
  }
  backing="$(readlink -f "$backing")"
  case "$backing" in
    /tmp/*|/var/tmp/*|"${RUNNER_TEMP:-/__xodus_no_runner_temp__}"/*)
      ;;
    *)
      echo "REFUSE: loop backing file is outside an approved temporary path: $backing" >&2
      exit 10
      ;;
  esac

  echo "APPROVED DISPOSABLE INSTALL TARGET: $target"
  echo "backing_file=$backing"
  echo "size_bytes=$size_bytes"
  exit 0
fi

# Physical disks remain locked unless a human deliberately opts in. This is a
# second boundary in addition to the project-level live-boot-only policy.
[[ "${XODUS_ALLOW_PHYSICAL_INSTALL:-}" == "YES-I-UNDERSTAND" ]] || {
  echo "REFUSE: physical installation is locked; Thursday validation is live-boot-only" >&2
  exit 11
}

echo "APPROVED PHYSICAL INSTALL TARGET: $target"
echo "size_bytes=$size_bytes"

#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/write-candidate-usb.sh [--yes] [--dry-run] <candidate-dir> <disk-device>

Safely writes a qualified Xodus hardware-candidate ISO to an entire removable/test disk.
The target must be a whole block disk (for example /dev/sdb), not a partition.

Options:
  --yes      Skip the final typed confirmation (intended for controlled automation only).
  --dry-run  Perform every safety/provenance check but do not write to the target.
EOF
}

ASSUME_YES=0
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) break ;;
  esac
done

[[ $# -eq 2 ]] || { usage >&2; exit 2; }
CANDIDATE_DIR="$1"
DEVICE="$2"

for cmd in jq sha256sum find lsblk findmnt blockdev; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "error: required command '$cmd' is not installed" >&2
    exit 2
  }
done

[[ -d "$CANDIDATE_DIR" ]] || { echo "error: candidate directory not found: $CANDIDATE_DIR" >&2; exit 3; }
MANIFEST="$CANDIDATE_DIR/hardware-candidate.json"
[[ -s "$MANIFEST" ]] || { echo "error: missing hardware-candidate.json in $CANDIDATE_DIR" >&2; exit 3; }

CANDIDATE_SHA="$(jq -er '.candidate_sha' "$MANIFEST")"
POLICY="$(jq -er '.policy' "$MANIFEST")"
[[ "$POLICY" == "live-boot-only" ]] || {
  echo "error: unexpected candidate policy '$POLICY'; refusing to write an unrecognized artifact" >&2
  exit 4
}

mapfile -t ISO_FILES < <(find "$CANDIDATE_DIR" -maxdepth 2 -type f -name '*.iso' -print)
[[ ${#ISO_FILES[@]} -eq 1 ]] || {
  echo "error: expected exactly one ISO under $CANDIDATE_DIR; found ${#ISO_FILES[@]}" >&2
  exit 5
}
ISO="${ISO_FILES[0]}"

CHECKSUM_FILE="$(find "$CANDIDATE_DIR" -maxdepth 2 -type f \( -name '*.sha256' -o -name 'SHA256SUMS' \) -print -quit)"
[[ -n "$CHECKSUM_FILE" ]] || { echo "error: no SHA-256 checksum file found beside candidate ISO" >&2; exit 5; }
(
  cd "$(dirname "$CHECKSUM_FILE")"
  sha256sum -c "$(basename "$CHECKSUM_FILE")"
)

[[ -b "$DEVICE" ]] || { echo "error: target is not a block device: $DEVICE" >&2; exit 6; }
DEVICE="$(readlink -f "$DEVICE")"
DEVICE_TYPE="$(lsblk -dnro TYPE "$DEVICE" 2>/dev/null || true)"
[[ "$DEVICE_TYPE" == "disk" ]] || {
  echo "error: target must be a whole disk, not a partition or mapper device: $DEVICE (type=${DEVICE_TYPE:-unknown})" >&2
  exit 6
}

ROOT_SOURCE="$(findmnt -nro SOURCE / 2>/dev/null || true)"
ROOT_DISK=""
if [[ -n "$ROOT_SOURCE" && -b "$ROOT_SOURCE" ]]; then
  ROOT_REAL="$(readlink -f "$ROOT_SOURCE")"
  ROOT_PKNAME="$(lsblk -nro PKNAME "$ROOT_REAL" 2>/dev/null | head -n1 || true)"
  if [[ -n "$ROOT_PKNAME" ]]; then
    ROOT_DISK="$(readlink -f "/dev/$ROOT_PKNAME")"
  elif [[ "$(lsblk -dnro TYPE "$ROOT_REAL" 2>/dev/null || true)" == "disk" ]]; then
    ROOT_DISK="$ROOT_REAL"
  fi
fi
if [[ -n "$ROOT_DISK" && "$DEVICE" == "$ROOT_DISK" ]]; then
  echo "error: refusing to overwrite the disk backing the running root filesystem: $DEVICE" >&2
  exit 7
fi

MOUNTED="$(lsblk -nrpo NAME,MOUNTPOINT "$DEVICE" | awk '$2 != "" {print $1 " -> " $2}')"
if [[ -n "$MOUNTED" ]]; then
  echo "error: target disk or one of its partitions is mounted:" >&2
  echo "$MOUNTED" >&2
  echo "unmount it explicitly before retrying; this script will not auto-unmount disks" >&2
  exit 8
fi

ISO_BYTES="$(stat -c '%s' "$ISO")"
DEVICE_BYTES="$(blockdev --getsize64 "$DEVICE")"
if (( ISO_BYTES > DEVICE_BYTES )); then
  echo "error: ISO (${ISO_BYTES} bytes) does not fit target (${DEVICE_BYTES} bytes)" >&2
  exit 9
fi

MODEL="$(lsblk -dnro MODEL "$DEVICE" 2>/dev/null | sed 's/[[:space:]]*$//' || true)"
SERIAL="$(lsblk -dnro SERIAL "$DEVICE" 2>/dev/null | sed 's/[[:space:]]*$//' || true)"
SIZE="$(lsblk -dnro SIZE "$DEVICE" 2>/dev/null || true)"

cat <<EOF
Qualified Xodus candidate ready to write.
Candidate SHA: $CANDIDATE_SHA
Policy:        $POLICY
ISO:           $ISO
Target disk:   $DEVICE
Target size:   ${SIZE:-unknown}
Target model:  ${MODEL:-unknown}
Target serial: ${SERIAL:-unknown}

WARNING: writing the ISO destroys the existing partition table and data on $DEVICE.
The candidate policy remains LIVE BOOT ONLY; do not install Xodus to an internal disk yet.
EOF

if (( DRY_RUN )); then
  echo "dry-run: all provenance and target safety checks passed; no bytes written"
  exit 0
fi

if (( ! ASSUME_YES )); then
  if [[ ! -t 0 ]]; then
    echo "error: interactive confirmation requires a terminal; use --yes only after independently verifying the target" >&2
    exit 10
  fi
  printf 'Type the exact target device (%s) to confirm: ' "$DEVICE"
  read -r CONFIRM
  [[ "$CONFIRM" == "$DEVICE" ]] || { echo "aborted: confirmation did not match target device" >&2; exit 10; }
fi

if [[ $EUID -eq 0 ]]; then
  DD=(dd)
else
  command -v sudo >/dev/null 2>&1 || { echo "error: sudo is required to write the target disk" >&2; exit 11; }
  DD=(sudo dd)
fi

"${DD[@]}" if="$ISO" of="$DEVICE" bs=16M status=progress conv=fsync
if command -v sync >/dev/null 2>&1; then sync; fi
if command -v udevadm >/dev/null 2>&1; then udevadm settle || true; fi

echo "USB write completed successfully: $DEVICE"
echo "Candidate SHA: $CANDIDATE_SHA"
echo "Next: boot the target PC from this USB and follow docs/THURSDAY_HARDWARE_TEST.md."

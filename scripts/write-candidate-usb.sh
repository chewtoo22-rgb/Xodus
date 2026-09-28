#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/write-candidate-usb.sh [--yes] [--dry-run] <candidate-dir> <disk-device>
       scripts/write-candidate-usb.sh --verify-bundle <candidate-dir>

Safely writes a qualified Xodus hardware-candidate ISO to an entire removable/test disk.
The target must be a whole block disk (for example /dev/sdb), not a partition.

Options:
  --yes      Skip the final typed confirmation (intended for controlled automation only).
  --dry-run  Perform every safety/provenance check but do not write to the target.
  --verify-bundle  Verify the candidate files without checking or writing a disk.
EOF
}

ASSUME_YES=0
DRY_RUN=0
VERIFY_BUNDLE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --verify-bundle) VERIFY_BUNDLE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) break ;;
  esac
done

if (( VERIFY_BUNDLE )); then
  [[ $# -eq 1 && $ASSUME_YES -eq 0 && $DRY_RUN -eq 0 ]] || { usage >&2; exit 2; }
else
  [[ $# -eq 2 ]] || { usage >&2; exit 2; }
fi
CANDIDATE_DIR="$1"
DEVICE="${2:-}"

for cmd in jq sha256sum find sed tr; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "error: required command '$cmd' is not installed" >&2
    exit 2
  }
done

[[ -d "$CANDIDATE_DIR" ]] || { echo "error: candidate directory not found: $CANDIDATE_DIR" >&2; exit 3; }
MANIFEST="$CANDIDATE_DIR/hardware-candidate.json"
[[ -s "$MANIFEST" ]] || { echo "error: missing hardware-candidate.json in $CANDIDATE_DIR" >&2; exit 3; }

# The manifest and checksum check this local bundle for consistency. Fetch it
# through fetch-qualified-candidate.sh, which checks the GitHub run provenance.
if ! jq -e '
  .schema == 1 and
  (.candidate_sha | strings | test("^[0-9a-f]{40}$")) and
  .policy == "live-boot-only" and
  (.core_iso.run_id | numbers | . > 0 and floor == .) and
  (.core_iso.artifact_id | numbers | . > 0 and floor == .) and
  (.core_iso.artifact_name | strings | test("^xodus-reference-iso-[0-9a-f]{40}$")) and
  (.qa_qemu.run_id | numbers | . > 0 and floor == .) and
  .core_iso.run_id != .qa_qemu.run_id
' "$MANIFEST" >/dev/null; then
  echo "error: malformed qualification manifest or unrecognized candidate policy" >&2
  exit 4
fi
CANDIDATE_SHA="$(jq -er '.candidate_sha' "$MANIFEST")"
POLICY="$(jq -er '.policy' "$MANIFEST")"

mapfile -d '' -t ISO_FILES < <(find "$CANDIDATE_DIR" -type f -name '*.iso' -print0)
[[ ${#ISO_FILES[@]} -eq 1 ]] || {
  echo "error: expected exactly one ISO under $CANDIDATE_DIR; found ${#ISO_FILES[@]}" >&2
  exit 5
}
ISO="${ISO_FILES[0]}"
[[ -s "$ISO" ]] || { echo "error: candidate ISO is empty" >&2; exit 5; }
ISO_NAME="${ISO##*/}"
[[ "$ISO_NAME" =~ ^Xodus-reference-[A-Za-z0-9._-]+\.iso$ ]] || {
  echo "error: unexpected ISO filename: $ISO_NAME" >&2
  exit 5
}

mapfile -d '' -t CHECKSUM_FILES < <(find "$CANDIDATE_DIR" -type f -name 'xodus-reference.sha256' -print0)
[[ ${#CHECKSUM_FILES[@]} -eq 1 ]] || {
  echo "error: expected exactly one xodus-reference.sha256; found ${#CHECKSUM_FILES[@]}" >&2
  exit 5
}
mapfile -t CHECKSUM_LINES < "${CHECKSUM_FILES[0]}"
CHECKSUM_PATTERN='^([0-9a-fA-F]{64})  (pearos-iso/Xodus-reference-[A-Za-z0-9._-]+\.iso)$'
[[ ${#CHECKSUM_LINES[@]} -eq 1 && "${CHECKSUM_LINES[0]}" =~ $CHECKSUM_PATTERN ]] || {
  echo "error: malformed producer SHA-256 checksum" >&2
  exit 5
}
EXPECTED_SHA="${BASH_REMATCH[1],,}"
CHECKSUM_PATH="${BASH_REMATCH[2]}"
[[ "${CHECKSUM_PATH#pearos-iso/}" == "$ISO_NAME" ]] || {
  echo "error: checksum identifies a different ISO" >&2
  exit 5
}
ACTUAL_SHA="$(sha256sum "$ISO")"
ACTUAL_SHA="${ACTUAL_SHA%% *}"
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || {
  echo "error: candidate ISO SHA-256 verification failed" >&2
  exit 5
}

mapfile -d '' -t PRODUCER_FILES < <(find "$CANDIDATE_DIR" -type f -name 'xodus-reference.manifest' -print0)
[[ ${#PRODUCER_FILES[@]} -eq 1 ]] || {
  echo "error: expected exactly one xodus-reference.manifest; found ${#PRODUCER_FILES[@]}" >&2
  exit 5
}
mapfile -t PRODUCER_LINES < "${PRODUCER_FILES[0]}"
[[ ${#PRODUCER_LINES[@]} -eq 6 ]] || {
  echo "error: malformed ISO producer manifest" >&2
  exit 5
}
UPSTREAM_SHA="${PRODUCER_LINES[2]#upstream_commit=}"
INSTALLER_SHA="${PRODUCER_LINES[3]#installer_commit=}"
INSTALLER_LOCK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)/upstream/installer.lock"
[[ -f "$INSTALLER_LOCK" ]] || { echo "error: local installer lock is missing" >&2; exit 5; }
LOCKED_INSTALLER_SHA="$(sed -n 's/^REF=//p' "$INSTALLER_LOCK" | tr -d '\r')"
ARTIFACT_NAME="$(jq -er '.core_iso.artifact_name' "$MANIFEST")"
[[ "${PRODUCER_LINES[0]}" == 'schema=2' &&
   "${PRODUCER_LINES[1]}" == "xodus_source_commit=$CANDIDATE_SHA" &&
   "${PRODUCER_LINES[2]}" == "upstream_commit=$UPSTREAM_SHA" &&
   "$UPSTREAM_SHA" =~ ^[0-9a-f]{40}$ &&
   "$ARTIFACT_NAME" == "xodus-reference-iso-$UPSTREAM_SHA" &&
   "${PRODUCER_LINES[3]}" == "installer_commit=$INSTALLER_SHA" &&
   "$INSTALLER_SHA" =~ ^[0-9a-f]{40}$ &&
   "$INSTALLER_SHA" == "$LOCKED_INSTALLER_SHA" &&
   "${PRODUCER_LINES[4]}" == "iso_filename=$ISO_NAME" &&
   "${PRODUCER_LINES[5]}" == "iso_sha256=$EXPECTED_SHA" ]] || {
  echo "error: ISO producer manifest does not match candidate SHA, source locks, artifact, filename, or checksum" >&2
  exit 5
}

echo "Candidate bundle internally consistent: $ISO ($ACTUAL_SHA)"
if (( VERIFY_BUNDLE )); then
  exit 0
fi

for cmd in lsblk findmnt blockdev readlink stat awk sed; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "error: required command '$cmd' is not installed" >&2
    exit 2
  }
done

ISO_BYTES="$(stat -c '%s' "$ISO")"
[[ "$ISO_BYTES" =~ ^[0-9]+$ ]] || { echo "error: cannot determine ISO size" >&2; exit 5; }
DEVICE_INPUT="$DEVICE"

# Capture the target twice: once for the user to inspect and once immediately
# before dd. Resolve the original input again so a changed /dev/disk/by-id link
# cannot silently redirect the write after confirmation (or with --yes).
check_target() {
  [[ -b "$DEVICE_INPUT" ]] || { echo "error: target is not a block device: $DEVICE_INPUT" >&2; exit 6; }
  TARGET_DEVICE="$(readlink -f -- "$DEVICE_INPUT")" || {
    echo "error: cannot resolve target: $DEVICE_INPUT" >&2; exit 6;
  }
  [[ -b "$TARGET_DEVICE" ]] || { echo "error: resolved target is not a block device: $TARGET_DEVICE" >&2; exit 6; }
  TARGET_TYPE="$(lsblk -dnro TYPE "$TARGET_DEVICE" 2>/dev/null)" || {
    echo "error: cannot determine target type: $TARGET_DEVICE" >&2; exit 6;
  }
  [[ "$TARGET_TYPE" == disk ]] || {
    echo "error: target must be a whole disk, not a partition or mapper device: $TARGET_DEVICE (type=${TARGET_TYPE:-unknown})" >&2
    exit 6
  }
  TARGET_MAJMIN="$(lsblk -dnro MAJ:MIN "$TARGET_DEVICE" 2>/dev/null)" || {
    echo "error: cannot determine target device number: $TARGET_DEVICE" >&2; exit 6;
  }
  [[ "$TARGET_MAJMIN" =~ ^[0-9]+:[0-9]+$ ]] || {
    echo "error: invalid target device number: $TARGET_MAJMIN" >&2; exit 6;
  }
  TARGET_NODE_STAT="$(stat -Lc '%D:%i:%t:%T' "$TARGET_DEVICE")" || {
    echo "error: cannot identify target device node: $TARGET_DEVICE" >&2; exit 6;
  }

  ROOT_SOURCE="$(findmnt -nro SOURCE / 2>/dev/null)" || {
    echo "error: cannot identify the running root filesystem" >&2; exit 7;
  }
  ROOT_SOURCE="${ROOT_SOURCE%%\[*}"
  [[ -b "$ROOT_SOURCE" ]] || {
    echo "error: cannot identify the block device backing the running root filesystem: $ROOT_SOURCE" >&2
    exit 7
  }
  ROOT_REAL="$(readlink -f -- "$ROOT_SOURCE")" || {
    echo "error: cannot resolve the running root filesystem device" >&2; exit 7;
  }
  ROOT_ANCESTORS="$(lsblk -snrpo NAME "$ROOT_REAL" 2>/dev/null)" || {
    echo "error: cannot inspect disks backing the running root filesystem" >&2; exit 7;
  }
  [[ -n "$ROOT_ANCESTORS" ]] || {
    echo "error: no backing disks found for the running root filesystem" >&2; exit 7;
  }
  while IFS= read -r backing; do
    [[ -n "$backing" ]] || continue
    backing="$(readlink -f -- "$backing")" || {
      echo "error: cannot resolve a root backing device" >&2; exit 7;
    }
    if [[ "$TARGET_DEVICE" == "$backing" ]]; then
      echo "error: refusing to overwrite a disk backing the running root filesystem: $TARGET_DEVICE" >&2
      exit 7
    fi
  done <<< "$ROOT_ANCESTORS"

  MOUNTED="$(lsblk -nrpo NAME,MOUNTPOINT "$TARGET_DEVICE" | awk '$2 != "" {print $1 " -> " $2}')" || {
    echo "error: cannot inspect target mounts: $TARGET_DEVICE" >&2; exit 8;
  }
  if [[ -n "$MOUNTED" ]]; then
    echo "error: target disk or one of its partitions is mounted:" >&2
    echo "$MOUNTED" >&2
    echo "unmount it explicitly before retrying; this script will not auto-unmount disks" >&2
    exit 8
  fi

  TARGET_BYTES="$(blockdev --getsize64 "$TARGET_DEVICE")" || {
    echo "error: cannot determine target capacity: $TARGET_DEVICE" >&2; exit 9;
  }
  [[ "$TARGET_BYTES" =~ ^[0-9]+$ ]] || {
    echo "error: invalid target capacity: $TARGET_BYTES" >&2; exit 9;
  }
  if (( ISO_BYTES > TARGET_BYTES )); then
    echo "error: ISO (${ISO_BYTES} bytes) does not fit target (${TARGET_BYTES} bytes)" >&2
    exit 9
  fi

  TARGET_MODEL="$(lsblk -dnro MODEL "$TARGET_DEVICE" 2>/dev/null | sed 's/[[:space:]]*$//')" || {
    echo "error: cannot determine target model" >&2; exit 6;
  }
  TARGET_SERIAL="$(lsblk -dnro SERIAL "$TARGET_DEVICE" 2>/dev/null | sed 's/[[:space:]]*$//')" || {
    echo "error: cannot determine target serial" >&2; exit 6;
  }
  TARGET_SIZE="$(lsblk -dnro SIZE "$TARGET_DEVICE" 2>/dev/null)" || {
    echo "error: cannot determine target size" >&2; exit 6;
  }
}

check_target
EXPECTED_DEVICE="$TARGET_DEVICE"
EXPECTED_MAJMIN="$TARGET_MAJMIN"
EXPECTED_NODE_STAT="$TARGET_NODE_STAT"
EXPECTED_BYTES="$TARGET_BYTES"
EXPECTED_MODEL="$TARGET_MODEL"
EXPECTED_SERIAL="$TARGET_SERIAL"
EXPECTED_SIZE="$TARGET_SIZE"
DEVICE="$TARGET_DEVICE"
MODEL="$TARGET_MODEL"
SERIAL="$TARGET_SERIAL"
SIZE="$TARGET_SIZE"

cat <<EOF
Xodus candidate bundle ready to write.
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
  echo "dry-run: bundle consistency and target safety checks passed; no bytes written"
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
  sudo -v || { echo "error: sudo authorization failed" >&2; exit 11; }
  DD=(sudo dd)
fi

# Recheck the image after confirmation, then re-resolve the original disk input.
# All target checks must pass again, and every identity field must match.
PREWRITE_SHA="$(sha256sum "$ISO")"
PREWRITE_SHA="${PREWRITE_SHA%% *}"
[[ "$PREWRITE_SHA" == "$EXPECTED_SHA" ]] || {
  echo "error: candidate ISO changed after verification; refusing to write" >&2; exit 5;
}
check_target
if [[ "$TARGET_DEVICE" != "$EXPECTED_DEVICE" ||
      "$TARGET_MAJMIN" != "$EXPECTED_MAJMIN" ||
      "$TARGET_NODE_STAT" != "$EXPECTED_NODE_STAT" ||
      "$TARGET_BYTES" != "$EXPECTED_BYTES" ||
      "$TARGET_MODEL" != "$EXPECTED_MODEL" ||
      "$TARGET_SERIAL" != "$EXPECTED_SERIAL" ||
      "$TARGET_SIZE" != "$EXPECTED_SIZE" ]]; then
  echo "error: target identity changed after confirmation; refusing to write" >&2
  exit 12
fi

"${DD[@]}" if="$ISO" of="$TARGET_DEVICE" bs=16M status=progress conv=fsync
if command -v sync >/dev/null 2>&1; then sync; fi
if command -v udevadm >/dev/null 2>&1; then udevadm settle || true; fi

echo "USB write completed successfully: $DEVICE"
echo "Candidate SHA: $CANDIDATE_SHA"
echo "Next: boot the target PC from this USB and follow docs/THURSDAY_HARDWARE_TEST.md."

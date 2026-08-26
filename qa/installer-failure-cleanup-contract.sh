#!/usr/bin/env bash
set -euo pipefail

outdir="${1:-installer-failure-cleanup-evidence}"
mkdir -p "$outdir"
outdir="$(realpath "$outdir")"

workdir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/xodus-installer-cleanup.XXXXXX")"
image="$workdir/disposable.img"
mountpoint_path="$workdir/mnt"
mkdir -p "$mountpoint_path"

printf 'workdir=%s\nimage=%s\nmountpoint=%s\n' "$workdir" "$image" "$mountpoint_path" \
  > "$outdir/cleanup-contract-input.txt"

# Exercise the same class of host resources used by destructive installer CI,
# then force an error and require the EXIT trap to unwind everything.
set +e
sudo bash -s -- "$image" "$mountpoint_path" <<'ROOT_TEST'
set -euo pipefail
image="$1"
mountpoint_path="$2"
loopdev=""

cleanup() {
  rc=$?
  set +e
  if mountpoint -q "$mountpoint_path"; then
    umount "$mountpoint_path"
  fi
  if [[ -n "$loopdev" ]] && losetup "$loopdev" >/dev/null 2>&1; then
    losetup -d "$loopdev"
  fi
  rm -f "$image"
  exit "$rc"
}
trap cleanup EXIT INT TERM

truncate -s 128M "$image"
loopdev="$(losetup --find --show "$image")"
mkfs.ext4 -q -F "$loopdev"
mount "$loopdev" "$mountpoint_path"

echo XODUS_CLEANUP_PROBE > "$mountpoint_path/probe.txt"
sync

# Intentional failure: cleanup must still detach and unmount exact resources.
false
ROOT_TEST
probe_rc=$?
set -e

[[ "$probe_rc" -ne 0 ]] || {
  echo 'ERROR: intentional failure unexpectedly returned success' >&2
  exit 1
}

if mountpoint -q "$mountpoint_path"; then
  echo "ERROR: cleanup leaked mount $mountpoint_path" >&2
  exit 1
fi

if losetup -j "$image" | grep -q .; then
  echo "ERROR: cleanup leaked loop device for $image" >&2
  losetup -j "$image" >&2 || true
  exit 1
fi

if [[ -e "$image" ]]; then
  echo "ERROR: cleanup left disposable backing image behind" >&2
  exit 1
fi

printf 'intentional_failure_rc=%s\nmount_leaked=no\nloop_leaked=no\nbacking_image_leaked=no\ninstaller_failure_cleanup_contract=pass\n' \
  "$probe_rc" | tee "$outdir/cleanup-contract-summary.txt"

rmdir "$mountpoint_path" 2>/dev/null || true
rmdir "$workdir" 2>/dev/null || true

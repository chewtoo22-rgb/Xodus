#!/usr/bin/env bash
set -euo pipefail

iso="${1:-}"
outdir="${2:-qa-qga-contract-artifacts}"

if [[ -z "$iso" || ! -f "$iso" ]]; then
  echo "usage: $0 <qualified-xodus.iso> [evidence-dir]" >&2
  exit 2
fi

for cmd in unsquashfs mount umount find readlink; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing required command: $cmd" >&2; exit 69; }
done

iso="$(readlink -f "$iso")"
mkdir -p "$outdir"
outdir="$(readlink -f "$outdir")"
work="$(mktemp -d)"
iso_mount="$work/iso-mount"
mkdir -p "$iso_mount"
mounted=0
cleanup() {
  set +e
  if [[ "$mounted" -eq 1 ]]; then
    sudo umount "$iso_mount" >/dev/null 2>&1 || true
  fi
  sudo rm -rf "$work" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sudo mount -o loop,ro "$iso" "$iso_mount"
mounted=1
sfs="$(find "$iso_mount" -type f -name 'airootfs.sfs' -print -quit)"
[[ -n "$sfs" ]] || { echo "ERROR: airootfs.sfs not found" >&2; exit 3; }

listing="$work/qga-layout.full.txt"
unsquashfs -ll "$sfs" | awk '/qemu-ga$|qemu-guest-agent\.service|org\.qemu\.guest_agent\.0/ {print}' > "$listing"
cp "$listing" "$outdir/qga-layout.txt"

# unsquashfs prints symlinks as "squashfs-root/path -> target".  Reading $NF
# therefore returns the target instead of the enablement path.  Extract the
# squashfs-root path directly from each complete line so regular files and
# symlinks are handled identically.
path_matching() {
  local regex="$1"
  awk -v want="$regex" '
    {
      if (match($0, /squashfs-root\/[^[:space:]]+/)) {
        p = substr($0, RSTART, RLENGTH)
        sub(/^squashfs-root\//, "", p)
        if (p ~ want) { print p; exit }
      }
    }
  ' "$listing"
}

binary_rel="$(path_matching '(^|/)usr/bin/qemu-ga$')"
unit_rel="$(path_matching '(^|/)usr/lib/systemd/system/qemu-guest-agent\.service$')"
enabled_rel="$(path_matching '(^|/)multi-user\.target\.wants/qemu-guest-agent\.service$')"

binary_present=no
unit_present=no
enabled_on_boot=no
[[ -n "$binary_rel" ]] && binary_present=yes
[[ -n "$unit_rel" ]] && unit_present=yes
[[ -n "$enabled_rel" ]] && enabled_on_boot=yes

{
  echo "qga_binary_present=$binary_present"
  echo "qga_service_unit_present=$unit_present"
  echo "qga_enabled_on_boot=$enabled_on_boot"
  echo "qga_binary_path=${binary_rel:-missing}"
  echo "qga_unit_path=${unit_rel:-missing}"
  echo "qga_enablement_path=${enabled_rel:-missing}"
} | tee "$outdir/summary.txt"

if [[ "$binary_present" != yes || "$unit_present" != yes ]]; then
  echo "ERROR: qualified ISO lacks required qemu-guest-agent runtime surface" >&2
  exit 4
fi

# Do not treat package presence as proof that the live system starts QGA.
# The destructive installer gate requires a reachable guest-agent channel, so
# boot-time enablement is a separate invariant that must be visible in the image.
if [[ "$enabled_on_boot" != yes ]]; then
  echo "ERROR: qemu-guest-agent is present but not enabled in the live image" >&2
  exit 5
fi

echo "PASS: qualified ISO contains and enables qemu-guest-agent for live boot control."

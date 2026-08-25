#!/usr/bin/env bash
set -euo pipefail

outdir="${1:-qa-installer-partition-artifacts}"
disk_gib="${DISK_GIB:-32}"
mkdir -p "$outdir"
outdir="$(readlink -f "$outdir")"

for cmd in truncate losetup wipefs sgdisk partprobe udevadm mkfs.fat mkfs.ext4 lsblk mount umount findmnt; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: required command missing: $cmd" >&2
    exit 69
  }
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
guard="$repo_root/scripts/installer-target-guard.sh"
audit="$repo_root/scripts/audit-installer-driver.sh"
[[ -f "$guard" && -f "$audit" ]] || {
  echo "ERROR: installer guard/audit scripts are missing" >&2
  exit 66
}

# Refuse to exercise destructive geometry unless the pinned upstream installer
# still satisfies the exact driver contract this probe mirrors.
bash "$audit" "$repo_root/upstream/installer.lock" "$outdir/upstream-audit" \
  | tee "$outdir/installer-driver-contract.txt"

backing="${RUNNER_TEMP:-/tmp}/xodus-installer-partition-probe.raw"
truncate -s "${disk_gib}G" "$backing"
loop="$(sudo losetup --find --show --partscan "$backing")"

cleanup() {
  set +e
  for dev in "${loop}p1" "${loop}p2"; do
    mountpoint -q "$outdir/mnt-${dev##*/}" && sudo umount "$outdir/mnt-${dev##*/}" || true
  done
  sudo losetup -d "$loop" >/dev/null 2>&1 || true
  rm -f "$backing"
}
trap cleanup EXIT

export XODUS_DISPOSABLE=1
export XODUS_INSTALL_CONFIRM="$loop"
bash "$guard" "$loop" | tee "$outdir/target-guard.txt"

# Mirror the audited UEFI destructive boundary from the pinned pearOS setup:
# wipe whole disk, GPT, 512 MiB ESP, remaining Linux root, then format both.
sudo wipefs -a "$loop"
sudo sgdisk -o "$loop" >/dev/null
sudo sgdisk -n 1:0:+512M -n 2:0:0 -t 1:ef00 -t 2:8300 "$loop" >/dev/null
sudo partprobe "$loop"
sudo udevadm settle

boot="${loop}p1"
root="${loop}p2"
[[ -b "$boot" && -b "$root" ]] || {
  echo "ERROR: expected partition devices did not appear" >&2
  lsblk "$loop" >&2 || true
  exit 1
}

sudo mkfs.fat -F32 "$boot" >/dev/null
sudo mkfs.ext4 -F "$root" >/dev/null
sudo udevadm settle

lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,PARTTYPE,PARTLABEL "$loop" \
  | tee "$outdir/lsblk-after-format.txt"
sudo sgdisk -p "$loop" | tee "$outdir/gpt.txt"

efi_guid='c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
linux_guid='0fc63daf-8483-4772-8e79-3d69d8477de4'
boot_type="$(lsblk -ndo PARTTYPE "$boot" | tr '[:upper:]' '[:lower:]')"
root_type="$(lsblk -ndo PARTTYPE "$root" | tr '[:upper:]' '[:lower:]')"
boot_fs="$(lsblk -ndo FSTYPE "$boot")"
root_fs="$(lsblk -ndo FSTYPE "$root")"

[[ "$boot_type" == "$efi_guid" ]] || { echo "ERROR: ESP GUID mismatch: $boot_type" >&2; exit 1; }
[[ "$root_type" == "$linux_guid" ]] || { echo "ERROR: root GUID mismatch: $root_type" >&2; exit 1; }
[[ "$boot_fs" == "vfat" ]] || { echo "ERROR: ESP filesystem mismatch: $boot_fs" >&2; exit 1; }
[[ "$root_fs" == "ext4" ]] || { echo "ERROR: root filesystem mismatch: $root_fs" >&2; exit 1; }

mkdir -p "$outdir/mnt-${boot##*/}" "$outdir/mnt-${root##*/}"
sudo mount "$boot" "$outdir/mnt-${boot##*/}"
sudo mount "$root" "$outdir/mnt-${root##*/}"
findmnt "$outdir/mnt-${boot##*/}" | tee "$outdir/esp-mount.txt"
findmnt "$outdir/mnt-${root##*/}" | tee "$outdir/root-mount.txt"
sudo umount "$outdir/mnt-${boot##*/}"
sudo umount "$outdir/mnt-${root##*/}"

cat <<EOF | tee "$outdir/partition-probe-evidence.txt"
destructive_partition_probe=pass
installer_invoked=no
upstream_driver_contract=pass
target_guard=pass
target=$loop
backing_file=$backing
disk_gib=$disk_gib
partition_table=gpt
esp_guid=$boot_type
esp_fstype=$boot_fs
root_guid=$root_type
root_fstype=$root_fs
physical_install_policy=locked
EOF

echo "Guarded destructive partition probe passed. Full installer execution is still unproven."

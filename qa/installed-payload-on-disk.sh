#!/usr/bin/env bash
set -euo pipefail

image=${1:-}
outdir=${2:-}
[[ -n "$image" && -n "$outdir" ]] || {
  echo "Usage: qa/installed-payload-on-disk.sh <installed-disk> <output-dir>" >&2
  exit 64
}
[[ -f "$image" ]] || { echo "ERROR: installed disk image not found: $image" >&2; exit 66; }

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
system_contract="$repo_root/qa/installed-system-contract.sh"
boot_contract="$repo_root/qa/installed-boot-contract.sh"
[[ -f "$system_contract" && -f "$boot_contract" ]] || {
  echo "ERROR: installed payload contract dependency missing" >&2
  exit 66
}

mkdir -p "$outdir"
outdir=$(readlink -f "$outdir")
image=$(readlink -f "$image")
root_mnt="$outdir/root-mnt"
esp_mnt="$outdir/esp-mnt"
mkdir -p "$root_mnt" "$esp_mnt"

for cmd in qemu-img qemu-nbd lsblk mount umount sgdisk python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: required command missing: $cmd" >&2; exit 69; }
done

format=$(qemu-img info --output=json "$image" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("format", ""))')
[[ "$format" == raw || "$format" == qcow2 ]] || {
  echo "ERROR: unsupported installed disk image format: ${format:-unknown}" >&2
  exit 65
}

nbd=/dev/nbd1
cleanup() {
  set +e
  mountpoint -q "$esp_mnt" && sudo umount "$esp_mnt"
  mountpoint -q "$root_mnt" && sudo umount "$root_mnt"
  if [[ -e "$nbd" ]]; then
    sudo qemu-nbd --disconnect "$nbd" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

sudo modprobe nbd max_part=16
sudo qemu-nbd --format="$format" --connect="$nbd" "$image"
sudo udevadm settle

sudo sgdisk -p "$nbd" | tee "$outdir/partition-table.txt"
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,PARTTYPE,PARTLABEL "$nbd" | tee "$outdir/lsblk.txt"

efi_guid='c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
linux_guid='0fc63daf-8483-4772-8e79-3d69d8477de4'
efi_dev=$(lsblk -nrpo PATH,PARTTYPE "$nbd" | awk -v guid="$efi_guid" 'tolower($2)==guid {print $1; exit}')
root_dev=$(lsblk -nrpo PATH,PARTTYPE "$nbd" | awk -v guid="$linux_guid" 'tolower($2)==guid {print $1; exit}')
[[ -n "$efi_dev" ]] || { echo "ERROR: installed disk has no EFI System Partition" >&2; exit 1; }
[[ -n "$root_dev" ]] || { echo "ERROR: installed disk has no Linux root/data partition" >&2; exit 1; }

sudo mount -o ro "$root_dev" "$root_mnt"
sudo mount -o ro "$efi_dev" "$esp_mnt"

bash "$system_contract" "$root_mnt" "$outdir/system"
bash "$boot_contract" "$root_mnt" "$esp_mnt" "$outdir/boot"

{
  echo "installed_payload_on_disk=pass"
  echo "installed_system_contract=pass"
  echo "installed_boot_contract=pass"
  echo "image_format=$format"
  echo "efi_partition=$efi_dev"
  echo "root_partition=$root_dev"
  echo "physical_hardware_claim=not_automatic"
} | tee "$outdir/installed-payload-summary.txt"

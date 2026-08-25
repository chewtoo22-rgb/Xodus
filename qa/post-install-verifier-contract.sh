#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
verifier="$repo_root/qa/post-install-uefi-smoke.sh"
work=${1:-"$repo_root/.tmp/post-install-verifier-contract"}
mkdir -p "$work"

for cmd in qemu-img qemu-nbd sgdisk lsblk; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: required command missing: $cmd" >&2; exit 69; }
done
[[ -f "$verifier" ]] || { echo "ERROR: verifier not found: $verifier" >&2; exit 66; }

sudo modprobe nbd max_part=16

cleanup_nbd() {
  sudo qemu-nbd --disconnect /dev/nbd0 >/dev/null 2>&1 || true
}
trap cleanup_nbd EXIT

expect_reject() {
  local name=$1 image=$2 expected=$3
  local out="$work/$name-out"
  local log="$work/$name.log"
  rm -rf "$out"
  mkdir -p "$out"

  set +e
  bash "$verifier" "$image" "$out" >"$log" 2>&1
  rc=$?
  set -e

  if [[ $rc -eq 0 ]]; then
    echo "ERROR: verifier accepted adversarial image: $name" >&2
    cat "$log" >&2
    exit 1
  fi
  if ! grep -Fq "$expected" "$log"; then
    echo "ERROR: verifier rejected $name for an unexpected reason" >&2
    echo "Expected diagnostic: $expected" >&2
    cat "$log" >&2
    exit 1
  fi
  echo "PASS: $name rejected as expected ($expected)"
}

make_image() {
  local image=$1
  rm -f "$image"
  qemu-img create -f qcow2 "$image" 32G >/dev/null
}

# Case 1: a completely blank target must never count as an installed system.
blank="$work/blank.qcow2"
make_image "$blank"
expect_reject blank "$blank" "installed disk has no EFI System Partition"

# Case 2: an ESP alone is not an installed OS. This catches firmware-only
# false positives where OVMF has somewhere to look but no Linux root exists.
efi_only="$work/efi-only.qcow2"
make_image "$efi_only"
sudo qemu-nbd --connect=/dev/nbd0 "$efi_only"
sudo sgdisk --zap-all /dev/nbd0 >/dev/null
sudo sgdisk -n 1:1MiB:+512MiB -t 1:ef00 -c 1:XODUS_EFI /dev/nbd0 >/dev/null
sudo partprobe /dev/nbd0
sudo udevadm settle
cleanup_nbd
expect_reject efi_only "$efi_only" "installed disk has no Linux root/data partition"

# Case 3: partition labels/types alone are insufficient. A fake GPT with both
# expected partition types but no filesystems/userspace must still be rejected.
empty_layout="$work/empty-layout.qcow2"
make_image "$empty_layout"
sudo qemu-nbd --connect=/dev/nbd0 "$empty_layout"
sudo sgdisk --zap-all /dev/nbd0 >/dev/null
sudo sgdisk -n 1:1MiB:+512MiB -t 1:ef00 -c 1:XODUS_EFI /dev/nbd0 >/dev/null
sudo sgdisk -n 2:0:0 -t 2:8300 -c 2:XODUS_ROOT /dev/nbd0 >/dev/null
sudo partprobe /dev/nbd0
sudo udevadm settle
cleanup_nbd

set +e
bash "$verifier" "$empty_layout" "$work/empty-layout-out" >"$work/empty-layout.log" 2>&1
rc=$?
set -e
if [[ $rc -eq 0 ]]; then
  echo "ERROR: verifier accepted an unformatted fake installed layout" >&2
  cat "$work/empty-layout.log" >&2
  exit 1
fi

echo "PASS: empty GPT layout rejected before boot proof"
echo "Post-install verifier adversarial contract passed."

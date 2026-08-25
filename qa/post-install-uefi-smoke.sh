#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: qa/post-install-uefi-smoke.sh <installed-disk.qcow2> <output-dir>

Validates an installed Xodus VM disk independently of the installer ISO.
The gate fails unless the image has a sane GPT layout with EFI + Linux root
partitions and remains alive under UEFI QEMU boot for the watchdog window.
EOF
}

[[ $# -eq 2 ]] || { usage >&2; exit 64; }

image=$1
outdir=$2
watchdog=${XODUS_POSTINSTALL_WATCHDOG_SECONDS:-90}

[[ -f "$image" ]] || { echo "ERROR: installed disk image not found: $image" >&2; exit 66; }
mkdir -p "$outdir"

for cmd in qemu-img qemu-system-x86_64 sgdisk; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: required command missing: $cmd" >&2; exit 69; }
done

format=$(qemu-img info --output=json "$image" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("format", ""))')
[[ "$format" == "qcow2" || "$format" == "raw" ]] || {
  echo "ERROR: unsupported installed disk image format: ${format:-unknown}" >&2
  exit 65
}

# qemu-nbd is the least ambiguous way to inspect a qcow2 partition table.
command -v qemu-nbd >/dev/null 2>&1 || { echo "ERROR: qemu-nbd is required" >&2; exit 69; }
command -v lsblk >/dev/null 2>&1 || { echo "ERROR: lsblk is required" >&2; exit 69; }

nbd=/dev/nbd0
cleanup() {
  set +e
  if [[ -e "$nbd" ]]; then
    sudo qemu-nbd --disconnect "$nbd" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

sudo modprobe nbd max_part=16
sudo qemu-nbd --connect="$nbd" "$image"
sudo udevadm settle

sudo sgdisk -p "$nbd" | tee "$outdir/partition-table.txt"
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,PARTTYPE,PARTLABEL "$nbd" | tee "$outdir/lsblk.txt"

mapfile -t parttypes < <(lsblk -nrpo PARTTYPE "$nbd" | sed '/^$/d' | tr '[:upper:]' '[:lower:]')

# UEFI system partition GUID and generic Linux filesystem GUID.
efi_guid='c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
linux_guid='0fc63daf-8483-4772-8e79-3d69d8477de4'

printf '%s\n' "${parttypes[@]}" | grep -qx "$efi_guid" || {
  echo "ERROR: installed disk has no EFI System Partition" >&2
  exit 1
}
printf '%s\n' "${parttypes[@]}" | grep -qx "$linux_guid" || {
  echo "ERROR: installed disk has no Linux root/data partition" >&2
  exit 1
}

sudo qemu-nbd --disconnect "$nbd"

find_ovmf() {
  local code vars
  for code in \
    /usr/share/OVMF/OVMF_CODE_4M.fd \
    /usr/share/OVMF/OVMF_CODE.fd \
    /usr/share/edk2/x64/OVMF_CODE.fd; do
    [[ -f "$code" ]] || continue
    case "$code" in
      *_4M.fd) vars=${code/CODE_4M/VARS_4M} ;;
      *) vars=${code/CODE/VARS} ;;
    esac
    [[ -f "$vars" ]] || continue
    printf '%s\n%s\n' "$code" "$vars"
    return 0
  done
  return 1
}

mapfile -t ovmf < <(find_ovmf) || true
[[ ${#ovmf[@]} -eq 2 ]] || {
  echo "ERROR: OVMF firmware pair not found" >&2
  find /usr/share -maxdepth 3 -type f -name 'OVMF*.fd' -print >&2 2>/dev/null || true
  exit 69
}

cp "${ovmf[1]}" "$outdir/OVMF_VARS.fd"
serial="$outdir/post-install-serial.log"
qemu_log="$outdir/qemu.log"

set +e
timeout --preserve-status "$watchdog" qemu-system-x86_64 \
  -machine q35,accel=tcg \
  -cpu max \
  -m 4096 \
  -smp 2 \
  -nodefaults \
  -no-reboot \
  -display none \
  -serial "file:$serial" \
  -monitor none \
  -drive "if=pflash,format=raw,readonly=on,file=${ovmf[0]}" \
  -drive "if=pflash,format=raw,file=$outdir/OVMF_VARS.fd" \
  -drive "if=virtio,format=$format,file=$image" \
  >"$qemu_log" 2>&1
rc=$?
set -e

case "$rc" in
  124|143)
    # Staying alive until the watchdog is the minimum independent-boot signal.
    ;;
  0)
    echo "ERROR: installed VM exited before watchdog; independent boot not proven" >&2
    exit 1
    ;;
  *)
    echo "ERROR: QEMU failed during post-install UEFI boot (rc=$rc)" >&2
    tail -n 100 "$qemu_log" >&2 || true
    exit "$rc"
    ;;
esac

{
  echo "post_install_uefi_boot=pass"
  echo "installer_iso_attached=no"
  echo "watchdog_seconds=$watchdog"
  echo "image_format=$format"
} | tee "$outdir/post-install-evidence.txt"

echo "Post-install UEFI smoke gate passed."

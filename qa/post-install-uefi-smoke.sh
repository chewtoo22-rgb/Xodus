#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: qa/post-install-uefi-smoke.sh <installed-disk.qcow2> <output-dir>

Validates an installed Xodus VM disk independently of the installer ISO.
The gate requires:
  * GPT with EFI System + Linux root partitions
  * an EFI executable on the ESP
  * a real Linux userspace on the root filesystem
  * a systemd boot sentinel emitted from the installed userspace over ttyS0

The verifier injects only a CI sentinel unit into the installed root filesystem,
then boots the disk with NO installer ISO attached. Firmware idling is not a pass.
EOF
}

[[ $# -eq 2 ]] || { usage >&2; exit 64; }

image=$1
outdir=$2
watchdog=${XODUS_POSTINSTALL_WATCHDOG_SECONDS:-120}
sentinel='XODUS_POSTINSTALL_BOOT_OK'

[[ -f "$image" ]] || { echo "ERROR: installed disk image not found: $image" >&2; exit 66; }
mkdir -p "$outdir"

for cmd in qemu-img qemu-nbd qemu-system-x86_64 sgdisk lsblk mount umount python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: required command missing: $cmd" >&2; exit 69; }
done

format=$(qemu-img info --output=json "$image" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("format", ""))')
[[ "$format" == "qcow2" || "$format" == "raw" ]] || {
  echo "ERROR: unsupported installed disk image format: ${format:-unknown}" >&2
  exit 65
}

nbd=/dev/nbd0
root_mnt="$outdir/root-mnt"
efi_mnt="$outdir/efi-mnt"
mkdir -p "$root_mnt" "$efi_mnt"

cleanup() {
  set +e
  mountpoint -q "$efi_mnt" && sudo umount "$efi_mnt"
  mountpoint -q "$root_mnt" && sudo umount "$root_mnt"
  if [[ -e "$nbd" ]]; then
    sudo qemu-nbd --disconnect "$nbd" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

sudo modprobe nbd max_part=16
# qemu-img already established the exact image format above. Pass it through
# to qemu-nbd instead of allowing format probing; probing raw media can impose
# write restrictions on sector 0 and abort this verifier before partition proof.
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

sudo mount -o ro "$efi_dev" "$efi_mnt"
mapfile -t efi_bins < <(sudo find "$efi_mnt" -type f -iname '*.efi' -print 2>/dev/null)
[[ ${#efi_bins[@]} -gt 0 ]] || {
  echo "ERROR: EFI System Partition contains no .efi executable" >&2
  exit 1
}
printf '%s\n' "${efi_bins[@]}" | sed "s#^$efi_mnt##" | tee "$outdir/efi-executables.txt"
sudo umount "$efi_mnt"

sudo mount "$root_dev" "$root_mnt"
[[ -f "$root_mnt/etc/os-release" ]] || { echo "ERROR: root filesystem lacks /etc/os-release" >&2; exit 1; }
[[ -x "$root_mnt/usr/lib/systemd/systemd" || -x "$root_mnt/sbin/init" ]] || {
  echo "ERROR: root filesystem lacks a usable init/userspace" >&2
  exit 1
}
sudo cp "$root_mnt/etc/os-release" "$outdir/installed-os-release.txt"

unit="$root_mnt/etc/systemd/system/xodus-ci-boot-sentinel.service"
sudo tee "$unit" >/dev/null <<EOF
[Unit]
Description=Xodus CI post-install boot sentinel
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo $sentinel > /dev/ttyS0'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
sudo mkdir -p "$root_mnt/etc/systemd/system/multi-user.target.wants"
sudo ln -sfn ../xodus-ci-boot-sentinel.service \
  "$root_mnt/etc/systemd/system/multi-user.target.wants/xodus-ci-boot-sentinel.service"
sync
sudo umount "$root_mnt"
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

# Prefer hardware virtualization when CI exposes it. Keep a deterministic TCG
# fallback, but grant the slower path enough time that CPU emulation does not
# masquerade as a userspace boot regression.
if [[ -c /dev/kvm ]]; then
  sudo chmod 666 /dev/kvm >/dev/null 2>&1 || true
  qemu_machine='q35,accel=kvm'
  qemu_cpu='host'
  qemu_accel='kvm'
else
  qemu_machine='q35,accel=tcg'
  qemu_cpu='max'
  qemu_accel='tcg'
  if (( watchdog < 240 )); then
    watchdog=240
  fi
fi
printf 'qemu_accel=%s\nwatchdog_seconds=%s\ninstaller_iso_attached=no\n' \
  "$qemu_accel" "$watchdog" | tee "$outdir/post-install-runtime.txt"

set +e
timeout "$watchdog" qemu-system-x86_64 \
  -machine "$qemu_machine" \
  -cpu "$qemu_cpu" \
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

if ! grep -Fqx "$sentinel" "$serial" 2>/dev/null; then
  echo "ERROR: installed userspace never emitted the boot sentinel (qemu rc=$rc, accel=$qemu_accel)" >&2
  tail -n 160 "$serial" >&2 2>/dev/null || true
  tail -n 120 "$qemu_log" >&2 2>/dev/null || true
  exit 1
fi

{
  echo "post_install_uefi_boot=pass"
  echo "userspace_sentinel=$sentinel"
  echo "installer_iso_attached=no"
  echo "watchdog_seconds=$watchdog"
  echo "qemu_accel=$qemu_accel"
  echo "image_format=$format"
  echo "efi_partition=$efi_dev"
  echo "root_partition=$root_dev"
} | tee "$outdir/post-install-evidence.txt"

echo "Post-install UEFI userspace gate passed."

#!/usr/bin/env bash
set -euo pipefail

ISO_PATH="${1:-}"
LOG_DIR="${2:-qa-installer-artifacts}"
DISK_GIB="${DISK_GIB:-32}"
BOOT_SECONDS="${BOOT_SECONDS:-120}"

if [[ -z "$ISO_PATH" || ! -f "$ISO_PATH" ]]; then
  echo "usage: $0 <iso-path> [log-dir]" >&2
  exit 2
fi

mkdir -p "$LOG_DIR"
DISK_PATH="$LOG_DIR/xodus-installer-target.qcow2"

command -v qemu-system-x86_64 >/dev/null
command -v qemu-img >/dev/null
command -v xorriso >/dev/null

file "$ISO_PATH" | tee "$LOG_DIR/iso-file.txt"
xorriso -indev "$ISO_PATH" -report_el_torito as_mkisofs >"$LOG_DIR/el-torito.txt" 2>&1
if ! grep -Eqi 'EFI|UEFI|eltorito' "$LOG_DIR/el-torito.txt"; then
  echo "ISO does not advertise an EFI/El Torito boot path" >&2
  exit 3
fi

qemu-img create -f qcow2 "$DISK_PATH" "${DISK_GIB}G" | tee "$LOG_DIR/qemu-img-create.txt"
qemu-img info "$DISK_PATH" | tee "$LOG_DIR/qemu-img-info.txt"

OVMF_CODE=""
OVMF_VARS=""
for candidate in \
  /usr/share/OVMF/OVMF_CODE_4M.fd \
  /usr/share/OVMF/OVMF_CODE.fd \
  /usr/share/edk2/x64/OVMF_CODE.fd \
  /usr/share/edk2-ovmf/x64/OVMF_CODE.fd; do
  [[ -f "$candidate" ]] && { OVMF_CODE="$candidate"; break; }
done
for candidate in \
  /usr/share/OVMF/OVMF_VARS_4M.fd \
  /usr/share/OVMF/OVMF_VARS.fd \
  /usr/share/edk2/x64/OVMF_VARS.fd \
  /usr/share/edk2-ovmf/x64/OVMF_VARS.fd; do
  [[ -f "$candidate" ]] && { OVMF_VARS="$candidate"; break; }
done

if [[ -z "$OVMF_CODE" ]]; then
  echo "Unable to locate OVMF firmware" >&2
  exit 4
fi

QEMU_FW_ARGS=(-drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE")
if [[ -n "$OVMF_VARS" ]]; then
  cp "$OVMF_VARS" "$LOG_DIR/OVMF_VARS.fd"
  QEMU_FW_ARGS+=(-drive "if=pflash,format=raw,file=$LOG_DIR/OVMF_VARS.fd")
fi

# Rehearsal only: attach an expendable installer target and prove the live ISO
# remains bootable in the exact topology used by the future destructive test.
# No installer automation is invoked here.
set +e
timeout --signal=TERM --kill-after=10s "${BOOT_SECONDS}s" \
  qemu-system-x86_64 \
    -machine q35,accel=tcg \
    -cpu max \
    -m 3072 \
    -smp 2 \
    "${QEMU_FW_ARGS[@]}" \
    -drive "file=$DISK_PATH,if=virtio,format=qcow2,cache=writeback" \
    -cdrom "$ISO_PATH" \
    -boot order=d \
    -display none \
    -monitor none \
    -serial "file:$LOG_DIR/serial.log" \
    -no-reboot
QEMU_RC=$?
set -e

if [[ "$QEMU_RC" -ne 124 && "$QEMU_RC" -ne 0 ]]; then
  echo "QEMU exited unexpectedly with code $QEMU_RC" >&2
  tail -n 200 "$LOG_DIR/serial.log" 2>/dev/null || true
  exit "$QEMU_RC"
fi

qemu-img info "$DISK_PATH" >"$LOG_DIR/post-rehearsal-disk-info.txt"
printf 'qemu_exit=%s\nwatchdog_seconds=%s\ndisk_gib=%s\ndisk_path=%s\nfirmware=%s\nvars=%s\ninstaller_invoked=no\n' \
  "$QEMU_RC" "$BOOT_SECONDS" "$DISK_GIB" "$DISK_PATH" "$OVMF_CODE" "${OVMF_VARS:-none}" \
  | tee "$LOG_DIR/rehearsal-summary.txt"

echo "Installer VM rehearsal completed: UEFI live ISO stayed up with an expendable target attached."

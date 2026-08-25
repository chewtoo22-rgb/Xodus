#!/usr/bin/env bash
set -euo pipefail

ISO_PATH="${1:-}"
LOG_DIR="${2:-qa-artifacts}"
BOOT_SECONDS="${BOOT_SECONDS:-90}"

if [[ -z "$ISO_PATH" || ! -f "$ISO_PATH" ]]; then
  echo "usage: $0 <iso-path> [log-dir]" >&2
  exit 2
fi

mkdir -p "$LOG_DIR"

file "$ISO_PATH" | tee "$LOG_DIR/iso-file.txt"
xorriso -indev "$ISO_PATH" -report_el_torito as_mkisofs >"$LOG_DIR/el-torito.txt" 2>&1

if ! grep -Eqi 'EFI|UEFI|eltorito' "$LOG_DIR/el-torito.txt"; then
  echo "ISO does not advertise an EFI/El Torito boot path" >&2
  cat "$LOG_DIR/el-torito.txt" >&2
  exit 3
fi

OVMF_CODE=""
OVMF_VARS=""
for candidate in \
  /usr/share/OVMF/OVMF_CODE_4M.fd \
  /usr/share/OVMF/OVMF_CODE.fd \
  /usr/share/edk2/x64/OVMF_CODE.fd \
  /usr/share/edk2-ovmf/x64/OVMF_CODE.fd; do
  if [[ -f "$candidate" ]]; then
    OVMF_CODE="$candidate"
    break
  fi
done

for candidate in \
  /usr/share/OVMF/OVMF_VARS_4M.fd \
  /usr/share/OVMF/OVMF_VARS.fd \
  /usr/share/edk2/x64/OVMF_VARS.fd \
  /usr/share/edk2-ovmf/x64/OVMF_VARS.fd; do
  if [[ -f "$candidate" ]]; then
    OVMF_VARS="$candidate"
    break
  fi
done

if [[ -z "$OVMF_CODE" ]]; then
  echo "Unable to locate OVMF firmware" >&2
  find /usr/share -maxdepth 4 -type f \( -iname 'OVMF*fd' -o -iname '*OVMF*.fd' \) -print 2>/dev/null | sort >&2 || true
  exit 4
fi

QEMU_FW_ARGS=(
  -drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE"
)

if [[ -n "$OVMF_VARS" ]]; then
  cp "$OVMF_VARS" "$LOG_DIR/OVMF_VARS.fd"
  QEMU_FW_ARGS+=(
    -drive "if=pflash,format=raw,file=$LOG_DIR/OVMF_VARS.fd"
  )
fi

set +e
timeout --signal=TERM --kill-after=10s "${BOOT_SECONDS}s" \
  qemu-system-x86_64 \
    -machine q35,accel=tcg \
    -cpu max \
    -m 2048 \
    -smp 2 \
    "${QEMU_FW_ARGS[@]}" \
    -cdrom "$ISO_PATH" \
    -boot order=d \
    -display none \
    -monitor none \
    -serial "file:$LOG_DIR/serial.log" \
    -no-reboot \
    -snapshot
QEMU_RC=$?
set -e

if [[ "$QEMU_RC" -ne 124 && "$QEMU_RC" -ne 0 ]]; then
  echo "QEMU exited unexpectedly with code $QEMU_RC" >&2
  tail -n 200 "$LOG_DIR/serial.log" 2>/dev/null || true
  exit "$QEMU_RC"
fi

printf 'qemu_exit=%s\nwatchdog_seconds=%s\nfirmware=%s\nvars=%s\n' \
  "$QEMU_RC" "$BOOT_SECONDS" "$OVMF_CODE" "${OVMF_VARS:-none}" \
  | tee "$LOG_DIR/smoke-summary.txt"
echo "UEFI boot smoke test completed without an early QEMU crash."

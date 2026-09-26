#!/usr/bin/env bash
set -euo pipefail

# The live image carries xodus-live-desktop-probe.service. Only that service,
# after checking SDDM, logind, KWin and Plasma in the guest, emits this line.
readonly SENTINEL='XODUS_LIVE_DESKTOP_READY'
ISO_PATH=${1:-}
LOG_DIR=${2:-qa-artifacts}
BOOT_SECONDS=${BOOT_SECONDS:-600}

if [[ -z "$ISO_PATH" || ! -f "$ISO_PATH" ]]; then
  echo "usage: $0 <iso-path> [log-dir]" >&2
  exit 2
fi
if [[ ! "$BOOT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "BOOT_SECONDS must be a positive integer" >&2
  exit 2
fi
for command in file xorriso qemu-system-x86_64 python3 awk realpath ps; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Missing required command: $command" >&2
    exit 69
  }
done

mkdir -p "$LOG_DIR"
LOG_DIR=$(cd "$LOG_DIR" && pwd -P)
ISO_PATH=$(realpath "$ISO_PATH")
file "$ISO_PATH" | tee "$LOG_DIR/iso-file.txt"
xorriso -indev "$ISO_PATH" -report_el_torito as_mkisofs >"$LOG_DIR/el-torito.txt" 2>&1
if ! grep -Eqi '(^|[[:space:]])-e[[:space:]]|EFI|UEFI' "$LOG_DIR/el-torito.txt"; then
  echo "ISO does not advertise an EFI boot path" >&2
  cat "$LOG_DIR/el-torito.txt" >&2
  exit 3
fi

# OVMF code and variables must belong to the same firmware layout. Explicit
# paths are useful for controlled local fixtures and custom distributions.
OVMF_CODE=${OVMF_CODE_PATH:-}
OVMF_VARS=${OVMF_VARS_PATH:-}
if [[ -n "$OVMF_CODE" || -n "$OVMF_VARS" ]]; then
  [[ -f "$OVMF_CODE" && -f "$OVMF_VARS" ]] || {
    echo "OVMF_CODE_PATH and OVMF_VARS_PATH must name an existing pair" >&2
    exit 4
  }
else
  for code in \
    /usr/share/OVMF/OVMF_CODE_4M.fd \
    /usr/share/OVMF/OVMF_CODE.fd \
    /usr/share/edk2/x64/OVMF_CODE.fd \
    /usr/share/edk2-ovmf/x64/OVMF_CODE.fd; do
    [[ -f "$code" ]] || continue
    case "$code" in
      *_4M.fd) vars=${code/CODE_4M/VARS_4M} ;;
      *) vars=${code/CODE/VARS} ;;
    esac
    if [[ -f "$vars" ]]; then
      OVMF_CODE=$code
      OVMF_VARS=$vars
      break
    fi
  done
  [[ -n "$OVMF_CODE" ]] || {
    echo "Unable to locate a matching OVMF code/variables pair" >&2
    exit 4
  }
fi
cp "$OVMF_VARS" "$LOG_DIR/OVMF_VARS.fd"

if [[ -c /dev/kvm && -r /dev/kvm && -w /dev/kvm ]]; then
  qemu_machine='q35,accel=kvm'
  qemu_cpu=host
  qemu_accel=kvm
else
  qemu_machine='q35,accel=tcg'
  qemu_cpu=max
  qemu_accel=tcg
fi

serial="$LOG_DIR/serial.log"
qemu_log="$LOG_DIR/qemu.log"
monitor="$LOG_DIR/qmp.sock"
: >"$serial"
: >"$qemu_log"
rm -f "$monitor"
qemu_pid=''
cleanup() {
  if [[ -n "$qemu_pid" ]] && kill -0 "$qemu_pid" 2>/dev/null; then
    kill "$qemu_pid" 2>/dev/null || true
    sleep 1
    kill -KILL "$qemu_pid" 2>/dev/null || true
  fi
  if [[ -n "$qemu_pid" ]]; then wait "$qemu_pid" 2>/dev/null || true; fi
  rm -f "$monitor"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

qemu-system-x86_64 \
  -machine "$qemu_machine" \
  -cpu "$qemu_cpu" \
  -m 4096 \
  -smp 2 \
  -drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE" \
  -drive "if=pflash,format=raw,file=$LOG_DIR/OVMF_VARS.fd" \
  -cdrom "$ISO_PATH" \
  -boot order=d \
  -display none \
  -vga virtio \
  -monitor none \
  -qmp "unix:$monitor,server=on,wait=off" \
  -serial stdio \
  -no-reboot \
  -snapshot \
  >"$serial" 2>"$qemu_log" &
qemu_pid=$!

capture_screen() {
  # A screenshot is diagnostic, not a pass condition. QMP can fail when the
  # firmware or display backend has not initialized yet.
  [[ -S "$monitor" ]] || return 0
  python3 - "$monitor" "$LOG_DIR/guest-screen.ppm" <<'PY' || true
import json
import socket
import sys

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(5)
try:
    sock.connect(sys.argv[1])
    stream = sock.makefile("rwb", buffering=0)
    stream.readline()  # QMP greeting
    stream.write(b'{"execute":"qmp_capabilities"}\n')
    while json.loads(stream.readline()).get("return") is None:
        pass
    request = {"execute": "screendump", "arguments": {"filename": sys.argv[2]}}
    stream.write((json.dumps(request) + "\n").encode())
    while True:
        response = json.loads(stream.readline())
        if "return" in response:
            break
        if "error" in response:
            print("QMP screendump failed:", response["error"], file=sys.stderr)
            break
except (OSError, ValueError, EOFError) as exc:
    print("QMP screenshot unavailable:", exc, file=sys.stderr)
finally:
    sock.close()
PY
}

exact_sentinel_seen() {
  # ttyS0 can use CRLF. Strip CR bytes only and require a complete exact line.
  awk -v sentinel="$SENTINEL" '
    { gsub(/\r/, ""); if ($0 == sentinel) found=1 }
    END { exit(found ? 0 : 1) }
  ' "$serial" 2>/dev/null
}

qemu_alive() {
  local state
  state=$(ps -o stat= -p "$qemu_pid" 2>/dev/null) || return 1
  [[ -n "$state" && "$state" != *Z* ]]
}

started=$SECONDS
deadline=$((SECONDS + BOOT_SECONDS))
ready=no
while (( SECONDS < deadline )); do
  if ! qemu_alive; then
    break
  fi
  if exact_sentinel_seen; then
    ready=yes
    break
  fi
  sleep 1
done

capture_screen
elapsed=$((SECONDS - started))
if [[ "$ready" != yes ]] || ! qemu_alive; then
  printf 'result=fail\nreason=guest_desktop_sentinel_missing\nwatchdog_seconds=%s\nelapsed_seconds=%s\nqemu_accel=%s\n' \
    "$BOOT_SECONDS" "$elapsed" "$qemu_accel" | tee "$LOG_DIR/smoke-summary.txt" >&2
  tail -n 160 "$serial" >&2 2>/dev/null || true
  tail -n 120 "$qemu_log" >&2 2>/dev/null || true
  exit 1
fi

printf 'result=pass\nguest_evidence=%s\nwatchdog_seconds=%s\nelapsed_seconds=%s\nqemu_accel=%s\nfirmware=%s\n' \
  "$SENTINEL" "$BOOT_SECONDS" "$elapsed" "$qemu_accel" "$OVMF_CODE" \
  | tee "$LOG_DIR/smoke-summary.txt"
echo "Live Xodus desktop session reached SDDM, logind, KWin and Plasma readiness."

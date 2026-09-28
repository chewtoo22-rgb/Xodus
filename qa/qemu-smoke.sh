#!/usr/bin/env bash
set -euo pipefail

# The live image carries xodus-live-desktop-probe.service. Only that service,
# after checking SDDM, logind, KWin and Plasma in the guest, emits this line.
readonly SENTINEL='XODUS_LIVE_DESKTOP_READY'
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
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
[[ -f "$script_dir/visible-frame.py" ]] || {
  echo 'Missing QEMU framebuffer visibility check' >&2
  exit 69
}

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
vnc="$LOG_DIR/guest-vnc.sock"
diagnostics="$LOG_DIR/qmp-status.log"
: >"$serial"
: >"$qemu_log"
: >"$diagnostics"
rm -f -- "$monitor" "$vnc" "$LOG_DIR/frame-evidence.txt" "$LOG_DIR/smoke-summary.txt" \
  "$LOG_DIR"/guest-screen-*.ppm
qemu_pid=''
cleanup() {
  if [[ -n "$qemu_pid" ]] && kill -0 "$qemu_pid" 2>/dev/null; then
    kill "$qemu_pid" 2>/dev/null || true
    sleep 1
    kill -KILL "$qemu_pid" 2>/dev/null || true
  fi
  if [[ -n "$qemu_pid" ]]; then wait "$qemu_pid" 2>/dev/null || true; fi
  rm -f "$monitor" "$vnc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# A local VNC display keeps the framebuffer active for QMP screenshots,
# without opening a TCP listener or a window on the CI runner.
qemu-system-x86_64 \
  -machine "$qemu_machine" \
  -cpu "$qemu_cpu" \
  -m 4096 \
  -smp 2 \
  -drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE" \
  -drive "if=pflash,format=raw,file=$LOG_DIR/OVMF_VARS.fd" \
  -cdrom "$ISO_PATH" \
  -boot order=d \
  -display "vnc=unix:$vnc" \
  -vga virtio \
  -monitor none \
  -qmp "unix:$monitor,server=on,wait=off" \
  -serial stdio \
  -no-reboot \
  -snapshot \
  >"$serial" 2>"$qemu_log" &
qemu_pid=$!

capture_diagnostics() {
  # A fresh framebuffer capture and the exact guest sentinel are both required
  # for readiness. Never reuse a screenshot from an earlier capture or run.
  local label=$1 elapsed=$2
  printf 'capture=%s elapsed_seconds=%s\n' "$label" "$elapsed" >>"$diagnostics"
  rm -f -- "$LOG_DIR/guest-screen-$label.ppm"
  if [[ ! -S "$monitor" ]]; then
    echo 'qmp=socket_unavailable' >>"$diagnostics"
    return 0
  fi
  python3 - "$monitor" "$LOG_DIR/guest-screen-$label.ppm" <<'PY' >>"$diagnostics" 2>&1 || true
import json
import socket
import sys

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(10)
try:
    sock.connect(sys.argv[1])
    stream = sock.makefile("rwb", buffering=0)
    if not stream.readline():
        raise EOFError("QMP greeting missing")

    def execute(command, arguments=None):
        request = {"execute": command, "id": command}
        if arguments is not None:
            request["arguments"] = arguments
        stream.write((json.dumps(request) + "\n").encode())
        while True:
            line = stream.readline()
            if not line:
                raise EOFError(f"QMP closed while waiting for {command}")
            response = json.loads(line)
            if response.get("id") == command:
                return response

    capabilities = execute("qmp_capabilities")
    if "error" in capabilities:
        raise RuntimeError(f"QMP capabilities failed: {capabilities['error']}")
    for command in ("query-status", "query-vnc"):
        print(f"{command}={json.dumps(execute(command), sort_keys=True)}")
    screen = execute("screendump", {"filename": sys.argv[2]})
    if "error" in screen:
        print(f"screendump_error={json.dumps(screen['error'], sort_keys=True)}")
    else:
        print(f"screendump={sys.argv[2]}")
except (OSError, ValueError, EOFError, RuntimeError) as exc:
    print("qmp_error=", exc)
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
next_capture=$((started + 20))
next_visible_capture=$started
guest_ready=no
ready=no
visible_frame=''
frame_report=''
while (( SECONDS < deadline )); do
  if ! qemu_alive; then
    break
  fi
  if exact_sentinel_seen; then
    guest_ready=yes
  fi
  if [[ "$guest_ready" == yes ]] && (( SECONDS >= next_visible_capture )); then
    elapsed=$((SECONDS - started))
    capture_diagnostics ready "$elapsed"
    visible_frame="$LOG_DIR/guest-screen-ready.ppm"
    if frame_report=$(python3 "$script_dir/visible-frame.py" "$visible_frame" 2>>"$diagnostics"); then
      if (( SECONDS < deadline )); then
        printf '%s\n' "$frame_report" | tee "$LOG_DIR/frame-evidence.txt"
        ready=yes
        break
      fi
      printf 'frame_check=late elapsed_seconds=%s %s\n' "$((SECONDS - started))" "$frame_report" >>"$diagnostics"
    fi
    printf 'frame_check=not_visible elapsed_seconds=%s %s\n' "$elapsed" "$frame_report" >>"$diagnostics"
    next_visible_capture=$((SECONDS + 10))
  elif (( SECONDS >= next_capture )); then
    capture_diagnostics "$((SECONDS - started))s" "$((SECONDS - started))"
    next_capture=$((SECONDS + 120))
  fi
  sleep 1
done

elapsed=$((SECONDS - started))
capture_diagnostics final "$elapsed"
if [[ "$ready" != yes ]] || ! qemu_alive; then
  reason=guest_desktop_sentinel_missing
  if [[ "$guest_ready" == yes ]]; then reason=guest_rendered_frame_missing; fi
  if ! qemu_alive; then reason=qemu_exited_before_desktop_ready; fi
  printf 'result=fail\nreason=%s\nwatchdog_seconds=%s\nelapsed_seconds=%s\nqemu_accel=%s\n' \
    "$reason" "$BOOT_SECONDS" "$elapsed" "$qemu_accel" | tee "$LOG_DIR/smoke-summary.txt" >&2
  tail -n 100 "$diagnostics" >&2 2>/dev/null || true
  tail -n 160 "$serial" >&2 2>/dev/null || true
  tail -n 120 "$qemu_log" >&2 2>/dev/null || true
  exit 1
fi

printf 'result=pass\nguest_evidence=%s\nrendered_frame=%s\n%s\nwatchdog_seconds=%s\nelapsed_seconds=%s\nqemu_accel=%s\nfirmware=%s\n' \
  "$SENTINEL" "$(basename "$visible_frame")" "$frame_report" "$BOOT_SECONDS" "$elapsed" "$qemu_accel" "$OVMF_CODE" \
  | tee "$LOG_DIR/smoke-summary.txt"
echo "Live Xodus desktop session reached SDDM, logind, KWin and Plasma readiness with a rendered frame."

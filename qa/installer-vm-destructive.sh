#!/usr/bin/env bash
set -euo pipefail

ISO_PATH="${1:-}"
OUTDIR="${2:-destructive-evidence}"
DISK_GIB="${DISK_GIB:-32}"
BOOT_SECONDS="${BOOT_SECONDS:-600}"
INSTALL_SECONDS="${INSTALL_SECONDS:-1800}"

if [[ -z "$ISO_PATH" || ! -f "$ISO_PATH" ]]; then
  echo "usage: $0 <iso-path> [output-dir]" >&2
  exit 64
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$OUTDIR"
OUTDIR="$(readlink -f "$OUTDIR")"
ISO_PATH="$(readlink -f "$ISO_PATH")"
DISK_ROOT="${RUNNER_TEMP:-/tmp}"
mkdir -p "$DISK_ROOT"
DISK_PATH="$DISK_ROOT/xodus-installed-${GITHUB_RUN_ID:-local}-$$.raw"
QGA_SOCK="$DISK_ROOT/xodus-qga-${GITHUB_RUN_ID:-local}-$$.sock"
LIVE_KERNEL="$DISK_ROOT/xodus-live-kernel-${GITHUB_RUN_ID:-local}-$$"
LIVE_INITRD="$DISK_ROOT/xodus-live-initrd-${GITHUB_RUN_ID:-local}-$$"

for cmd in truncate losetup qemu-system-x86_64 qemu-img python3 base64 git sha256sum lsblk xorriso blkid; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: required command missing: $cmd" >&2; exit 69; }
done

GUARD="$repo_root/scripts/installer-target-guard.sh"
AUDIT="$repo_root/scripts/audit-installer-driver.sh"
POST="$repo_root/qa/post-install-uefi-smoke.sh"
LOCK="$repo_root/upstream/installer.lock"
[[ -f "$GUARD" && -f "$AUDIT" && -f "$POST" && -f "$LOCK" ]] || {
  echo "ERROR: destructive gate dependency missing" >&2
  exit 66
}

AUDIT_DIR="$OUTDIR/installer-audit"
bash "$AUDIT" "$LOCK" "$AUDIT_DIR" | tee "$OUTDIR/driver-contract.txt"
# shellcheck disable=SC1090
source "$LOCK"
SETUP_FILE="$AUDIT_DIR/$SETUP_PATH"
[[ -s "$SETUP_FILE" ]] || { echo "ERROR: audited installer setup missing" >&2; exit 1; }
SETUP_B64="$(base64 -w0 "$SETUP_FILE")"

# Host-side destructive guard: approve the exact raw bytes that will later be
# attached to QEMU. The guard only accepts an explicitly disposable loop target
# backed by RUNNER_TEMP or /tmp.
truncate -s "${DISK_GIB}G" "$DISK_PATH"
loop_dev="$(sudo losetup --find --show "$DISK_PATH")"
qemu_pid=""
cleanup() {
  set +e
  if [[ -n "${qemu_pid:-}" ]]; then
    kill "$qemu_pid" >/dev/null 2>&1 || true
    wait "$qemu_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "${loop_dev:-}" ]]; then
    sudo losetup -d "$loop_dev" >/dev/null 2>&1 || true
  fi
  rm -f "$QGA_SOCK" "$DISK_PATH" "$LIVE_KERNEL" "$LIVE_INITRD" >/dev/null 2>&1 || true
}
trap cleanup EXIT

export XODUS_DISPOSABLE=1
export XODUS_INSTALL_CONFIRM="$loop_dev"
bash "$GUARD" "$loop_dev" | tee "$OUTDIR/target-guard.txt"
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS "$loop_dev" | tee "$OUTDIR/preinstall-lsblk.txt"
sudo losetup -d "$loop_dev"
loop_dev=""

find_ovmf() {
  local code vars
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
    [[ -f "$vars" ]] || continue
    printf '%s\n%s\n' "$code" "$vars"
    return 0
  done
  return 1
}

mapfile -t ovmf < <(find_ovmf) || true
[[ ${#ovmf[@]} -eq 2 ]] || { echo "ERROR: OVMF firmware pair not found" >&2; exit 69; }
cp "${ovmf[1]}" "$OUTDIR/OVMF_VARS_INSTALL.fd"

if [[ -c /dev/kvm ]]; then
  QEMU_MACHINE="q35,accel=kvm"
  QEMU_CPU="host"
  QEMU_ACCEL="kvm"
else
  QEMU_MACHINE="q35,accel=tcg"
  QEMU_CPU="max"
  QEMU_ACCEL="tcg"
fi

# pearOS's pinned profiledef.sh sets install_dir="arch". Keep the direct-kernel
# harness aligned with the actual built ISO rather than the source profile name
# (pear/). The ordinary boot smoke independently exercises the ISO bootloader.
ARCHISO_BASEDIR="arch"

# UEFI ISO boot is independently required by QA QEMU Boot Smoke. For this
# destructive installer gate, extract the kernel and initramfs from the exact
# checksum-verified ISO and boot that same live root deterministically. This
# avoids coupling installer automation to SDDM/Plymouth while still preserving
# the qualified ISO bytes, ArchISO live media, UEFI firmware, and audited
# installer payload under test.
xorriso -osirrox on -indev "$ISO_PATH" \
  -extract "/${ARCHISO_BASEDIR}/boot/x86_64/vmlinuz-linux" "$LIVE_KERNEL" \
  >"$OUTDIR/kernel-extract.log" 2>&1
xorriso -osirrox on -indev "$ISO_PATH" \
  -extract "/${ARCHISO_BASEDIR}/boot/x86_64/initramfs-linux.img" "$LIVE_INITRD" \
  >"$OUTDIR/initrd-extract.log" 2>&1
[[ -s "$LIVE_KERNEL" && -s "$LIVE_INITRD" ]] || {
  echo "ERROR: qualified ISO kernel/initramfs extraction failed" >&2
  exit 1
}
ISO_LABEL="$(blkid -s LABEL -o value "$ISO_PATH" || true)"
[[ -n "$ISO_LABEL" ]] || { echo "ERROR: qualified ISO volume label unavailable" >&2; exit 1; }
sha256sum "$LIVE_KERNEL" "$LIVE_INITRD" | tee "$OUTDIR/live-boot-payload.sha256"
printf 'iso_label=%s\narchisobasedir=%s\nqemu_accel=%s\nboot_timeout_seconds=%s\nlive_boot_mode=uefi-direct-kernel-from-qualified-iso\n' \
  "$ISO_LABEL" "$ARCHISO_BASEDIR" "$QEMU_ACCEL" "$BOOT_SECONDS" | tee "$OUTDIR/qemu-runtime.txt"

KERNEL_CMDLINE="archisobasedir=$ARCHISO_BASEDIR archisolabel=$ISO_LABEL cow_spacesize=4G module_blacklist=pcspkr nvme_load=yes console=tty0 console=ttyS0,115200n8 systemd.unit=multi-user.target systemd.mask=sddm.service systemd.show_status=true plymouth.enable=0"

qemu-system-x86_64 \
  -machine "$QEMU_MACHINE" \
  -cpu "$QEMU_CPU" \
  -m 4096 \
  -smp 2 \
  -no-reboot \
  -display none \
  -monitor none \
  -drive "if=pflash,format=raw,readonly=on,file=${ovmf[0]}" \
  -drive "if=pflash,format=raw,file=$OUTDIR/OVMF_VARS_INSTALL.fd" \
  -drive "file=$DISK_PATH,if=virtio,format=raw,cache=writeback" \
  -drive "file=$ISO_PATH,media=cdrom,readonly=on" \
  -kernel "$LIVE_KERNEL" \
  -initrd "$LIVE_INITRD" \
  -append "$KERNEL_CMDLINE" \
  -serial "file:$OUTDIR/install-serial.log" \
  -device virtio-rng-pci \
  -nic user,model=virtio-net-pci \
  -chardev "socket,path=$QGA_SOCK,server=on,wait=off,id=qga0" \
  -device virtio-serial-pci \
  -device virtserialport,chardev=qga0,name=org.qemu.guest_agent.0 \
  >"$OUTDIR/qemu.stdout" 2>"$OUTDIR/qemu.stderr" &
qemu_pid=$!
echo "$qemu_pid" >"$OUTDIR/qemu.pid"

QGA_HELPER="$OUTDIR/qga-run.py"
cat >"$QGA_HELPER" <<'PY'
#!/usr/bin/env python3
import argparse, base64, json, socket, sys, time

p = argparse.ArgumentParser()
p.add_argument("socket")
p.add_argument("mode", choices=["ping", "run"])
p.add_argument("--timeout", type=int, default=60)
p.add_argument("--command", default="true")
a = p.parse_args()

def connect():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(a.socket)
    return s, s.makefile("rwb", buffering=0)

def rpc(f, execute, arguments=None):
    req = {"execute": execute}
    if arguments is not None:
        req["arguments"] = arguments
    f.write((json.dumps(req) + "\n").encode())
    while True:
        line = f.readline()
        if not line:
            raise RuntimeError("QGA connection closed")
        msg = json.loads(line)
        if "error" in msg:
            raise RuntimeError(json.dumps(msg["error"]))
        if "return" in msg:
            return msg["return"]

deadline = time.time() + a.timeout
last = None
while time.time() < deadline:
    try:
        s, f = connect()
        rpc(f, "guest-ping")
        break
    except Exception as e:
        last = e
        time.sleep(2)
else:
    raise SystemExit(f"QGA not ready: {last}")

if a.mode == "ping":
    print("QGA_READY")
    raise SystemExit(0)

ret = rpc(f, "guest-exec", {
    "path": "/bin/bash",
    "arg": ["-lc", a.command],
    "capture-output": True,
})
pid = ret["pid"]
while time.time() < deadline:
    st = rpc(f, "guest-exec-status", {"pid": pid})
    if st.get("exited"):
        out = base64.b64decode(st.get("out-data", "")).decode(errors="replace")
        err = base64.b64decode(st.get("err-data", "")).decode(errors="replace")
        if out:
            print(out, end="")
        if err:
            print(err, end="", file=sys.stderr)
        raise SystemExit(st.get("exitcode", 1))
    time.sleep(2)
raise SystemExit("guest command timeout")
PY
chmod +x "$QGA_HELPER"

set +e
python3 "$QGA_HELPER" "$QGA_SOCK" ping --timeout "$BOOT_SECONDS" \
  >"$OUTDIR/qga-ping.log" 2>"$OUTDIR/qga-ping.err"
qga_rc=$?
set -e
if [[ $qga_rc -ne 0 ]]; then
  echo "ERROR: deterministic live userspace never exposed qemu-guest-agent" >&2
  printf 'qemu_alive_at_timeout=%s\n' "$(kill -0 "$qemu_pid" 2>/dev/null && echo yes || echo no)" \
    | tee -a "$OUTDIR/qemu-runtime.txt" >&2
  tail -n 160 "$OUTDIR/qemu.stderr" >&2 2>/dev/null || true
  tail -n 240 "$OUTDIR/install-serial.log" >&2 2>/dev/null || true
  cat "$OUTDIR/qga-ping.err" >&2 2>/dev/null || true
  exit 1
fi

echo "qga_live_boot=pass" | tee "$OUTDIR/live-control.txt"
python3 "$QGA_HELPER" "$QGA_SOCK" run --timeout 30 \
  --command 'systemctl is-system-running --wait || true; systemctl status qemu-guest-agent --no-pager || true; cat /etc/os-release' \
  >"$OUTDIR/live-system-status.txt" 2>"$OUTDIR/live-system-status.err"

TARGET_CMD='for d in /dev/vda /dev/sda /dev/nvme0n1; do test -b "$d" && { echo "$d"; exit 0; }; done; exit 1'
target_disk="$(python3 "$QGA_HELPER" "$QGA_SOCK" run --timeout 30 --command "$TARGET_CMD" | tr -d '\r\n')"
[[ "$target_disk" =~ ^/dev/(vd[a-z]+|sd[a-z]+|nvme[0-9]+n[0-9]+)$ ]] || {
  echo "ERROR: invalid guest target: $target_disk" >&2
  exit 1
}
printf 'guest_target=%s\n' "$target_disk" | tee "$OUTDIR/guest-target.txt"

INSTALL_CMD="set -e; mkdir -p /home/liveuser/Desktop; echo '$SETUP_B64' | base64 -d > /tmp/xodus-setup.sh; chmod 700 /tmp/xodus-setup.sh; bash /tmp/xodus-setup.sh '$target_disk'"
set +e
python3 "$QGA_HELPER" "$QGA_SOCK" run --timeout "$INSTALL_SECONDS" --command "$INSTALL_CMD" \
  >"$OUTDIR/installer.stdout" 2>"$OUTDIR/installer.stderr"
install_rc=$?
set -e
if [[ $install_rc -ne 0 ]]; then
  echo "ERROR: pinned installer exited with rc=$install_rc" >&2
  tail -n 200 "$OUTDIR/installer.stdout" >&2 2>/dev/null || true
  tail -n 200 "$OUTDIR/installer.stderr" >&2 2>/dev/null || true
  exit 1
fi

python3 "$QGA_HELPER" "$QGA_SOCK" run --timeout 30 --command 'sync' \
  >"$OUTDIR/sync.stdout" 2>"$OUTDIR/sync.stderr"

kill "$qemu_pid" >/dev/null 2>&1 || true
wait "$qemu_pid" >/dev/null 2>&1 || true
qemu_pid=""
rm -f "$QGA_SOCK"

qemu-img info "$DISK_PATH" | tee "$OUTDIR/postinstall-image-info.txt"
printf 'installer_execution=pass\nimage=%s\nformat=raw\ndisk_gib=%s\ncontrol=qemu-guest-agent\nlive_boot_mode=uefi-direct-kernel-from-qualified-iso\n' \
  "$DISK_PATH" "$DISK_GIB" | tee "$OUTDIR/install-evidence.txt"

# Independent proof: boot only the installed disk, with no installer ISO, and
# require the post-install verifier's userspace sentinel.
bash "$POST" "$DISK_PATH" "$OUTDIR/post-install"

{
  echo "destructive_vm_install_gate=pass"
  echo "target_guard=pass"
  echo "installer_driver_contract=pass"
  echo "qualified_iso_payload=pass"
  echo "live_iso_qga_control=pass"
  echo "installer_execution=pass"
  echo "post_install_uefi_userspace=pass"
  echo "physical_install_policy=still_locked_pending_human_validation"
} | tee "$OUTDIR/destructive-gate-summary.txt"

echo "Destructive VM install gate passed."

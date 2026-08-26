#!/usr/bin/env bash
set -euo pipefail

ISO_PATH="${1:-}"
OUTDIR="${2:-destructive-evidence}"
DISK_GIB="${DISK_GIB:-32}"
BOOT_SECONDS="${BOOT_SECONDS:-240}"
INSTALL_SECONDS="${INSTALL_SECONDS:-1800}"

if [[ -z "$ISO_PATH" || ! -f "$ISO_PATH" ]]; then
  echo "usage: $0 <iso-path> [output-dir]" >&2
  exit 64
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$OUTDIR"
OUTDIR="$(readlink -f "$OUTDIR")"
ISO_PATH="$(readlink -f "$ISO_PATH")"
DISK_PATH="$OUTDIR/xodus-installed.raw"

for cmd in truncate losetup qemu-system-x86_64 qemu-img expect base64 git sha256sum lsblk; do
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

# Fail closed if the pinned upstream installer drifted from the contract this
# driver expects. The audit workspace also provides the exact setup script that
# will be injected into the live ISO guest.
AUDIT_DIR="$OUTDIR/installer-audit"
bash "$AUDIT" "$LOCK" "$AUDIT_DIR" | tee "$OUTDIR/driver-contract.txt"
# shellcheck disable=SC1090
source "$LOCK"
SETUP_FILE="$AUDIT_DIR/$SETUP_PATH"
[[ -s "$SETUP_FILE" ]] || { echo "ERROR: audited installer setup missing" >&2; exit 1; }
SETUP_B64="$(base64 -w0 "$SETUP_FILE")"

# Use a sparse RAW image so the same bytes can be approved through a host loop
# device and then attached directly to QEMU. qcow2 must not be losetup'd.
truncate -s "${DISK_GIB}G" "$DISK_PATH"
loop_dev="$(sudo losetup --find --show "$DISK_PATH")"
cleanup_loop() {
  set +e
  if [[ -n "${loop_dev:-}" ]]; then
    sudo losetup -d "$loop_dev" >/dev/null 2>&1 || true
    loop_dev=""
  fi
}
trap cleanup_loop EXIT

export XODUS_DISPOSABLE=1
export XODUS_INSTALL_CONFIRM="$loop_dev"
bash "$GUARD" "$loop_dev" | tee "$OUTDIR/target-guard.txt"
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS "$loop_dev" | tee "$OUTDIR/preinstall-lsblk.txt"
cleanup_loop
trap - EXIT

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

EXPECT_SCRIPT="$OUTDIR/install.expect"
cat >"$EXPECT_SCRIPT" <<'EXPECT_EOF'
set timeout 30
set boot_deadline [expr {[clock seconds] + __BOOT_SECONDS__}]
log_file -noappend __SERIAL_LOG__
spawn qemu-system-x86_64 \
  -machine q35,accel=tcg \
  -cpu max \
  -m 4096 \
  -smp 2 \
  -no-reboot \
  -display none \
  -monitor none \
  -drive if=pflash,format=raw,readonly=on,file=__OVMF_CODE__ \
  -drive if=pflash,format=raw,file=__OVMF_VARS__ \
  -drive file=__DISK_PATH__,if=virtio,format=raw,cache=writeback \
  -cdrom __ISO_PATH__ \
  -boot order=d \
  -serial stdio

set got_prompt 0
while {!$got_prompt && [clock seconds] < $boot_deadline} {
  expect {
    -re {liveuser@[^#]*#|liveuser@[^$]*\$|root@[^#]*#|root@[^$]*\$} { set got_prompt 1 }
    "login:" {
      send "liveuser\r"
      expect {
        -re {Password:|password:} { send "pear\r"; expect -re {#|\$}; set got_prompt 1 }
        -re {liveuser@[^#]*#|liveuser@[^$]*\$|root@[^#]*#|root@[^$]*\$} { set got_prompt 1 }
        timeout { puts stderr "ERROR: login timeout"; exit 1 }
      }
    }
    timeout { }
    eof { puts stderr "ERROR: QEMU exited before shell"; exit 1 }
  }
}
if {!$got_prompt} { puts stderr "ERROR: boot timeout"; exit 1 }

send "for d in /dev/vda /dev/sda /dev/nvme0n1; do test -b \"\$d\" && echo \"\$d\"; done | head -n1 > /tmp/target_dev\r"
expect -re {#|\$}

send "cat /tmp/target_dev\r"
expect {
  -re {(/dev/[a-z0-9]+)} { set target_disk $expect_out(1,string) }
  timeout { puts stderr "ERROR: no target disk detected"; exit 1 }
}

send "echo '__SETUP_B64__' | base64 -d > /tmp/xodus-setup.sh && chmod +x /tmp/xodus-setup.sh\r"
expect -re {#|\$}

send "sudo bash /tmp/xodus-setup.sh $target_disk\r"
set timeout __INSTALL_SECONDS__
expect {
  -re {Installation finished} { puts "INSTALL_MARKER_SEEN"; exp_continue }
  eof { puts "QEMU_EOF_AFTER_INSTALL"; exit 0 }
  timeout { puts stderr "ERROR: installer timeout"; exit 1 }
}
EXPECT_EOF

python3 - "$EXPECT_SCRIPT" <<PY
from pathlib import Path
p = Path("$EXPECT_SCRIPT")
s = p.read_text()
repl = {
    "__BOOT_SECONDS__": "$BOOT_SECONDS",
    "__INSTALL_SECONDS__": "$INSTALL_SECONDS",
    "__SERIAL_LOG__": "$OUTDIR/install-serial.log",
    "__OVMF_CODE__": "${ovmf[0]}",
    "__OVMF_VARS__": "$OUTDIR/OVMF_VARS_INSTALL.fd",
    "__DISK_PATH__": "$DISK_PATH",
    "__ISO_PATH__": "$ISO_PATH",
    "__SETUP_B64__": "$SETUP_B64",
}
for k, v in repl.items():
    s = s.replace(k, v)
p.write_text(s)
PY

set +e
timeout --signal=TERM --kill-after=15s "$((BOOT_SECONDS + INSTALL_SECONDS + 60))s" \
  expect "$EXPECT_SCRIPT" >"$OUTDIR/expect.log" 2>"$OUTDIR/expect.err"
expect_rc=$?
set -e

if [[ $expect_rc -ne 0 ]]; then
  echo "ERROR: destructive installer driver failed (expect rc=$expect_rc)" >&2
  tail -n 120 "$OUTDIR/expect.log" >&2 2>/dev/null || true
  tail -n 120 "$OUTDIR/expect.err" >&2 2>/dev/null || true
  tail -n 120 "$OUTDIR/install-serial.log" >&2 2>/dev/null || true
  exit 1
fi

qemu-img info "$DISK_PATH" | tee "$OUTDIR/postinstall-image-info.txt"
printf 'installer_execution=pass\nimage=%s\nformat=raw\ndisk_gib=%s\n' \
  "$DISK_PATH" "$DISK_GIB" | tee "$OUTDIR/install-evidence.txt"

# Independent verifier: no installer ISO attached. It requires GPT, an ESP
# executable, a real Linux userspace and the ttyS0 systemd sentinel.
bash "$POST" "$DISK_PATH" "$OUTDIR/post-install"

{
  echo "destructive_vm_install_gate=pass"
  echo "target_guard=pass"
  echo "installer_driver_contract=pass"
  echo "installer_execution=pass"
  echo "post_install_uefi_userspace=pass"
  echo "physical_install_policy=still_locked_pending_human_validation"
} | tee "$OUTDIR/destructive-gate-summary.txt"

echo "Destructive VM install gate passed."

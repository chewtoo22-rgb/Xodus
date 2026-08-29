#!/usr/bin/env bash
set -euo pipefail

# Read-only preflight for the X1 physical NUC test. This script deliberately
# does not mount, partition, format, install, reboot, or modify firmware state.

fail=0
warn=0
pass() { printf 'PASS  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; warn=$((warn+1)); }
fail() { printf 'FAIL  %s\n' "$*"; fail=$((fail+1)); }

[[ $EUID -eq 0 ]] || warn "not running as root; some firmware/disk details may be incomplete"

if [[ -d /sys/firmware/efi ]]; then
  pass "booted in UEFI mode"
else
  fail "not booted in UEFI mode"
fi

if [[ -r /sys/firmware/efi/fw_platform_size ]]; then
  fw_bits=$(tr -cd '0-9' </sys/firmware/efi/fw_platform_size)
  [[ "$fw_bits" == "64" ]] && pass "64-bit UEFI firmware" || fail "unexpected UEFI platform size: ${fw_bits:-unknown}"
else
  warn "UEFI platform size unavailable"
fi

arch=$(uname -m)
[[ "$arch" == "x86_64" ]] && pass "x86_64 kernel" || fail "unexpected architecture: $arch"

mem_kib=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
if [[ "${mem_kib:-0}" -ge 7340032 ]]; then
  pass "memory >= 7 GiB ($(awk -v k="$mem_kib" 'BEGIN {printf "%.1f GiB", k/1048576}'))"
else
  fail "memory below X1 minimum: ${mem_kib:-unknown} KiB"
fi

root_src=$(findmnt -n -o SOURCE / 2>/dev/null || true)
root_fs=$(findmnt -n -o FSTYPE / 2>/dev/null || true)
printf 'INFO  root=%s fstype=%s\n' "${root_src:-unknown}" "${root_fs:-unknown}"
case "$root_fs" in overlay|squashfs|erofs|tmpfs|rootfs) pass "live/read-only root detected for pre-install test" ;; *) warn "root does not look like expected live media; verify test phase before destructive install" ;; esac

mapfile -t disks < <(lsblk -dn -o NAME,TYPE,SIZE,MODEL 2>/dev/null | awk '$2=="disk" {print}')
if ((${#disks[@]})); then
  printf 'INFO  candidate disks (read-only enumeration):\n'
  printf '      %s\n' "${disks[@]}"
else
  fail "no block disk detected"
fi

if command -v efibootmgr >/dev/null 2>&1; then
  efibootmgr >/dev/null 2>&1 && pass "EFI variable access available" || warn "efibootmgr present but EFI variables are not readable"
else
  warn "efibootmgr unavailable"
fi

if [[ -e /dev/dri/card0 || -e /dev/dri/renderD128 ]]; then
  pass "DRM graphics device present"
else
  warn "no DRM graphics device detected"
fi

if [[ -d /sys/class/net ]] && find /sys/class/net -mindepth 1 -maxdepth 1 ! -name lo -print -quit | grep -q .; then
  pass "non-loopback network interface present"
else
  warn "no non-loopback network interface detected"
fi

printf 'SUMMARY failures=%d warnings=%d destructive_actions=0\n' "$fail" "$warn"
(( fail == 0 ))

#!/usr/bin/env bash
set -euo pipefail

outdir="${1:-xodus-installed-hardware-evidence}"
mkdir -p "$outdir"
outdir="$(realpath "$outdir")"

run_capture() {
  local name="$1"
  shift
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n\n'
    "$@"
  } >"$outdir/$name.txt" 2>&1 || true
}

root_source="${XODUS_CONTRACT_ROOT_SOURCE:-$(findmnt -n -o SOURCE / 2>/dev/null || true)}"
root_fstype="${XODUS_CONTRACT_ROOT_FSTYPE:-$(findmnt -n -o FSTYPE / 2>/dev/null || true)}"

# This collector is intentionally for an independently booted installed system.
# Refuse common live/overlay roots so live-media success cannot be mislabeled as
# physical post-install success.
case "$root_source:$root_fstype" in
  *overlay*|*airootfs*|*squashfs*|*tmpfs*)
    printf 'refusing installed-system evidence on live/overlay root: source=%s fstype=%s\n' "$root_source" "$root_fstype" >&2
    exit 40
    ;;
esac

if [[ "${XODUS_CONTRACT_ALLOW_NO_EFI:-0}" != "1" && ! -d /sys/firmware/efi ]]; then
  printf 'refusing installed-system evidence: current boot is not UEFI\n' >&2
  exit 41
fi

printf 'captured_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$outdir/summary.txt"
printf 'hostname=%s\n' "$(hostname 2>/dev/null || true)" >> "$outdir/summary.txt"
printf 'kernel=%s\n' "$(uname -r)" >> "$outdir/summary.txt"
printf 'root_source=%s\n' "$root_source" >> "$outdir/summary.txt"
printf 'root_fstype=%s\n' "$root_fstype" >> "$outdir/summary.txt"
printf 'boot_mode=uefi\n' >> "$outdir/summary.txt"

if [[ -r /etc/os-release ]]; then
  cp /etc/os-release "$outdir/os-release.txt"
  . /etc/os-release
  printf 'os_pretty_name=%s\n' "${PRETTY_NAME:-unknown}" >> "$outdir/summary.txt"
fi

run_capture uname uname -a
run_capture findmnt-root findmnt -R /
run_capture lsblk lsblk -e7 -o NAME,PATH,TYPE,SIZE,RO,RM,TRAN,FSTYPE,FSVER,LABEL,UUID,PARTUUID,MOUNTPOINTS,MODEL,SERIAL
run_capture bootctl bootctl status
run_capture efibootmgr efibootmgr -v
run_capture system-default systemctl get-default
run_capture system-failed systemctl --failed --no-pager
run_capture display-manager systemctl status display-manager.service --no-pager
run_capture network-manager systemctl status NetworkManager.service --no-pager
run_capture bluetooth-service systemctl status bluetooth.service --no-pager
run_capture pipewire-user systemctl --user status pipewire.service --no-pager
run_capture ip-link ip link
run_capture ip-address ip address
run_capture rfkill rfkill list
run_capture bluetooth bluetoothctl show
run_capture audio-pactl pactl list short sinks
run_capture audio-aplay aplay -l
run_capture lspci lspci -nnk
run_capture lsusb lsusb
run_capture journal-errors journalctl -b -p warning..alert --no-pager
run_capture dmesg-errors dmesg --level=emerg,alert,crit,err,warn

root_block=""
if [[ "$root_source" == /dev/* ]]; then
  root_block="$root_source"
  pkname="$(lsblk -ndo PKNAME "$root_source" 2>/dev/null | head -n1 || true)"
  if [[ -n "$pkname" ]]; then
    root_block="/dev/$pkname"
  fi
fi
printf 'root_backing_disk=%s\n' "${root_block:-unknown}" >> "$outdir/summary.txt"

# Record installed boot artifacts without modifying them.
if [[ -d /boot ]]; then
  find /boot -maxdepth 4 -type f \( -iname '*.efi' -o -name 'grub.cfg' -o -name 'loader.conf' \) -printf '%p\n' 2>/dev/null \
    | sort > "$outdir/boot-artifacts.txt" || true
fi

printf 'collector=pass\n' >> "$outdir/summary.txt"
printf 'physical_install_claim=not_automatic\n' >> "$outdir/summary.txt"
printf 'Xodus installed-hardware evidence written to %s\n' "$outdir"

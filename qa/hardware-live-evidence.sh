#!/usr/bin/env bash
set -euo pipefail

outdir="${1:-xodus-hardware-evidence}"
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

printf 'captured_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$outdir/summary.txt"
printf 'hostname=%s\n' "$(hostname 2>/dev/null || true)" >> "$outdir/summary.txt"
printf 'kernel=%s\n' "$(uname -r)" >> "$outdir/summary.txt"

if [[ -r /etc/os-release ]]; then
  cp /etc/os-release "$outdir/os-release.txt"
  . /etc/os-release
  printf 'os_pretty_name=%s\n' "${PRETTY_NAME:-unknown}" >> "$outdir/summary.txt"
fi

run_capture uname uname -a
run_capture lsblk lsblk -e7 -o NAME,PATH,TYPE,SIZE,RO,RM,TRAN,FSTYPE,FSVER,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
run_capture findmnt findmnt -R /
run_capture lspci lspci -nnk
run_capture lsusb lsusb
run_capture ip-link ip link
run_capture ip-address ip address
run_capture rfkill rfkill list
run_capture bluetooth bluetoothctl show
run_capture audio-pactl pactl list short sinks
run_capture audio-aplay aplay -l
run_capture bootctl bootctl status
run_capture journal-warnings journalctl -b -p warning..alert --no-pager
run_capture system-failed systemctl --failed --no-pager
run_capture dmesg-errors dmesg --level=emerg,alert,crit,err,warn

# Record the disks backing mounted filesystems. This is read-only evidence used to
# detect surprising internal-disk involvement during live-boot validation.
if command -v findmnt >/dev/null 2>&1 && command -v lsblk >/dev/null 2>&1; then
  {
    printf 'source target backing_disk\n'
    findmnt -rn -o SOURCE,TARGET | while read -r source target; do
      [[ "$source" == /dev/* ]] || continue
      pkname="$(lsblk -ndo PKNAME "$source" 2>/dev/null | head -n1 || true)"
      if [[ -n "$pkname" ]]; then
        backing="/dev/$pkname"
      else
        backing="$source"
      fi
      printf '%s %s %s\n' "$source" "$target" "$backing"
    done
  } > "$outdir/mounted-block-devices.txt"
fi

printf 'collector=pass\n' >> "$outdir/summary.txt"
printf 'Xodus hardware evidence written to %s\n' "$outdir"

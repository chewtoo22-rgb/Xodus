#!/usr/bin/env bash
set -euo pipefail

requested_outdir="${1:-xodus-hardware-evidence}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="${XODUS_CANDIDATE_MANIFEST:-}"
candidate_sha="${XODUS_CANDIDATE_SHA:-}"
candidate_sha_source="environment"

if [[ -z "$candidate_sha" && -n "$manifest" ]]; then
  if [[ ! -f "$manifest" || -L "$manifest" || ! -r "$manifest" ]]; then
    printf 'candidate manifest must be a readable regular file, not a symlink: %s\n' "$manifest" >&2
    exit 3
  fi

  matches="$(grep -oE '"candidate_sha"[[:space:]]*:[[:space:]]*"[0-9a-fA-F]{40}"' "$manifest" || true)"
  match_count="$(printf '%s\n' "$matches" | grep -c . || true)"
  if [[ "$match_count" -ne 1 ]]; then
    printf 'candidate manifest must contain exactly one valid 40-character candidate_sha: %s\n' "$manifest" >&2
    exit 3
  fi
  candidate_sha="$(printf '%s\n' "$matches" | sed -E 's/.*"([0-9a-fA-F]{40})"$/\1/')"
  candidate_sha_source="manifest"
fi

if [[ -z "$candidate_sha" ]] && command -v git >/dev/null 2>&1; then
  candidate_sha="$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || true)"
  candidate_sha_source="git-checkout"
fi

if [[ ! "$candidate_sha" =~ ^[0-9a-fA-F]{40}$ ]]; then
  printf 'unable to resolve a valid 40-character Xodus candidate SHA\n' >&2
  printf 'set XODUS_CANDIDATE_SHA or XODUS_CANDIDATE_MANIFEST, or run from a Git checkout\n' >&2
  exit 3
fi
candidate_sha="${candidate_sha,,}"

if [[ -e "$requested_outdir" || -L "$requested_outdir" ]]; then
  printf 'evidence destination already exists; refusing to merge with stale or substituted evidence: %s\n' "$requested_outdir" >&2
  exit 4
fi

parent="$(dirname -- "$requested_outdir")"
leaf="$(basename -- "$requested_outdir")"
if [[ -z "$leaf" || "$leaf" == "." || "$leaf" == ".." ]]; then
  printf 'invalid evidence destination: %s\n' "$requested_outdir" >&2
  exit 4
fi
if [[ ! -d "$parent" || -L "$parent" ]]; then
  printf 'evidence destination parent must be an existing non-symlink directory: %s\n' "$parent" >&2
  exit 4
fi

parent="$(realpath "$parent")"
final_outdir="$parent/$leaf"
umask 077
staging_outdir="$(mktemp -d "$parent/.xodus-hardware-evidence.XXXXXX")"
cleanup() {
  if [[ -n "${staging_outdir:-}" && -d "$staging_outdir" ]]; then
    rm -rf -- "$staging_outdir"
  fi
}
trap cleanup EXIT INT TERM
outdir="$staging_outdir"

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
printf 'candidate_sha=%s\n' "$candidate_sha" >> "$outdir/summary.txt"
printf 'candidate_sha_source=%s\n' "$candidate_sha_source" >> "$outdir/summary.txt"
printf 'hardware_validation_claim=false\n' >> "$outdir/summary.txt"
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

# Publish only a complete bundle. Re-check the final name immediately before the
# rename so stale evidence is never silently merged or overwritten.
if [[ -e "$final_outdir" || -L "$final_outdir" ]]; then
  printf 'evidence destination appeared while collecting; refusing to overwrite it: %s\n' "$final_outdir" >&2
  exit 4
fi
mv -T -- "$staging_outdir" "$final_outdir"
staging_outdir=""
trap - EXIT INT TERM
printf 'Xodus hardware evidence written to %s\n' "$final_outdir"

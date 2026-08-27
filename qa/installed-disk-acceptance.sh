#!/usr/bin/env bash
set -euo pipefail

image=${1:-}
outdir=${2:-}
[[ -n "$image" && -n "$outdir" ]] || {
  echo "Usage: qa/installed-disk-acceptance.sh <installed-disk> <output-dir>" >&2
  exit 64
}
[[ -f "$image" ]] || {
  echo "ERROR: installed disk image not found: $image" >&2
  exit 66
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
payload="$repo_root/qa/installed-payload-on-disk.sh"
postinstall="$repo_root/qa/post-install-uefi-smoke.sh"
[[ -f "$payload" && -f "$postinstall" ]] || {
  echo "ERROR: installed-disk acceptance dependency missing" >&2
  exit 66
}

mkdir -p "$outdir"
outdir=$(readlink -f "$outdir")
image=$(readlink -f "$image")

bash "$payload" "$image" "$outdir/payload"
bash "$postinstall" "$image" "$outdir/boot"

{
  echo "installed_disk_acceptance=pass"
  echo "installed_payload_on_disk=pass"
  echo "post_install_uefi_userspace=pass"
  echo "physical_hardware_claim=not_automatic"
} | tee "$outdir/installed-disk-acceptance-summary.txt"

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

payload_summary="$outdir/payload/installed-payload-summary.txt"
[[ -f "$payload_summary" && ! -L "$payload_summary" ]] || {
  echo "ERROR: installed payload summary missing or unsafe" >&2
  exit 68
}

candidate_sha=$(sed -n 's/^candidate_sha=//p' "$payload_summary")
upstream_sha=$(sed -n 's/^upstream_sha=//p' "$payload_summary")
[[ "$candidate_sha" =~ ^[0-9a-f]{40}$ && "$upstream_sha" =~ ^[0-9a-f]{40}$ ]] || {
  echo "ERROR: installed payload provenance missing or malformed" >&2
  exit 68
}
[[ $(grep -c '^candidate_sha=' "$payload_summary") -eq 1 && $(grep -c '^upstream_sha=' "$payload_summary") -eq 1 ]] || {
  echo "ERROR: installed payload provenance is ambiguous" >&2
  exit 68
}

{
  echo "installed_disk_acceptance=pass"
  echo "installed_payload_on_disk=pass"
  echo "post_install_uefi_userspace=pass"
  echo "candidate_sha=$candidate_sha"
  echo "upstream_sha=$upstream_sha"
  echo "physical_hardware_claim=not_automatic"
} | tee "$outdir/installed-disk-acceptance-summary.txt"

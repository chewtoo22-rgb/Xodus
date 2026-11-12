#!/usr/bin/env bash
set -euo pipefail

root=${1:-}
[[ -n "$root" && -d "$root" ]] || {
  echo "Usage: qa/installed-build-provenance.sh <installed-root>" >&2
  exit 64
}

info="$root/usr/lib/xodus/build-info"
[[ -f "$info" && ! -L "$info" ]] || {
  echo "ERROR: installed build-info missing or unsafe" >&2
  exit 66
}

source_count=$(grep -Ec '^XODUS_SOURCE_COMMIT=[0-9a-f]{40}$' "$info" || true)
upstream_count=$(grep -Ec '^XODUS_UPSTREAM_COMMIT=[0-9a-f]{40}$' "$info" || true)
[[ "$source_count" -eq 1 && "$upstream_count" -eq 1 ]] || {
  echo "ERROR: installed build-info provenance schema invalid" >&2
  exit 67
}

# Reject duplicate/unknown XODUS provenance fields instead of silently choosing
# one. A qualification artifact should have exactly one identity, a concept
# humans occasionally rediscover after deployment.
xodus_lines=$(grep -Ec '^XODUS_[A-Z0-9_]+=' "$info" || true)
[[ "$xodus_lines" -eq 2 ]] || {
  echo "ERROR: installed build-info contains unexpected provenance fields" >&2
  exit 68
}

source_sha=$(sed -n 's/^XODUS_SOURCE_COMMIT=//p' "$info")
upstream_sha=$(sed -n 's/^XODUS_UPSTREAM_COMMIT=//p' "$info")

printf 'schema=1\n'
printf 'installed_build_provenance=pass\n'
printf 'candidate_sha=%s\n' "$source_sha"
printf 'upstream_sha=%s\n' "$upstream_sha"
printf 'hardware_validation_claim=false\n'

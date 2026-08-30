#!/usr/bin/env bash
set -euo pipefail

root=${1:-/}
expected=${XODUS_EXPECTED_SOURCE_COMMIT:-}
[[ -d "$root" ]] || { echo "ERROR: root missing" >&2; exit 64; }
[[ "$expected" =~ ^[0-9a-f]{40}$ ]] || { echo "ERROR: XODUS_EXPECTED_SOURCE_COMMIT must be an exact lowercase SHA" >&2; exit 65; }

info="$root/usr/lib/xodus/build-info"
[[ -f "$info" && ! -L "$info" ]] || { echo "ERROR: build-info missing or unsafe" >&2; exit 66; }

source_count=$(grep -Ec '^XODUS_SOURCE_COMMIT=[0-9a-f]{40}$' "$info" || true)
upstream_count=$(grep -Ec '^XODUS_UPSTREAM_COMMIT=[0-9a-f]{40}$' "$info" || true)
[[ "$source_count" -eq 1 && "$upstream_count" -eq 1 ]] || { echo "ERROR: build-info provenance schema invalid" >&2; exit 67; }

source_sha=$(sed -n 's/^XODUS_SOURCE_COMMIT=//p' "$info")
upstream_sha=$(sed -n 's/^XODUS_UPSTREAM_COMMIT=//p' "$info")
[[ "$source_sha" == "$expected" ]] || { echo "ERROR: installed source commit does not match candidate" >&2; exit 68; }

printf 'schema=1\n'
printf 'x1_build_info=pass\n'
printf 'candidate_sha=%s\n' "$source_sha"
printf 'upstream_sha=%s\n' "$upstream_sha"
printf 'hardware_validation_claim=false\n'

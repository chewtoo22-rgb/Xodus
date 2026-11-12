#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
verifier="$repo_root/qa/installed-build-provenance.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

source_sha=0123456789abcdef0123456789abcdef01234567
upstream_sha=89abcdef0123456789abcdef0123456789abcdef

make_root() {
  local name=$1
  local root="$work/$name"
  mkdir -p "$root/usr/lib/xodus"
  printf '%s\n' "$root"
}

expect_reject() {
  local name=$1 root=$2 expected=$3
  local log="$work/$name.log"
  set +e
  bash "$verifier" "$root" >"$log" 2>&1
  rc=$?
  set -e
  [[ $rc -ne 0 ]] || { echo "ERROR: accepted $name" >&2; cat "$log" >&2; exit 1; }
  grep -Fq "$expected" "$log" || { echo "ERROR: wrong rejection for $name" >&2; cat "$log" >&2; exit 1; }
}

valid=$(make_root valid)
printf 'XODUS_SOURCE_COMMIT=%s\nXODUS_UPSTREAM_COMMIT=%s\n' "$source_sha" "$upstream_sha" >"$valid/usr/lib/xodus/build-info"
out=$(bash "$verifier" "$valid")
grep -Fqx 'installed_build_provenance=pass' <<<"$out"
grep -Fqx "candidate_sha=$source_sha" <<<"$out"
grep -Fqx "upstream_sha=$upstream_sha" <<<"$out"
grep -Fqx 'hardware_validation_claim=false' <<<"$out"

missing=$(make_root missing)
expect_reject missing "$missing" 'installed build-info missing or unsafe'

symlinked=$(make_root symlinked)
printf 'XODUS_SOURCE_COMMIT=%s\nXODUS_UPSTREAM_COMMIT=%s\n' "$source_sha" "$upstream_sha" >"$work/external-build-info"
ln -s "$work/external-build-info" "$symlinked/usr/lib/xodus/build-info"
expect_reject symlinked "$symlinked" 'installed build-info missing or unsafe'

malformed=$(make_root malformed)
printf 'XODUS_SOURCE_COMMIT=NOT_A_SHA\nXODUS_UPSTREAM_COMMIT=%s\n' "$upstream_sha" >"$malformed/usr/lib/xodus/build-info"
expect_reject malformed "$malformed" 'installed build-info provenance schema invalid'

duplicate=$(make_root duplicate)
printf 'XODUS_SOURCE_COMMIT=%s\nXODUS_SOURCE_COMMIT=%s\nXODUS_UPSTREAM_COMMIT=%s\n' "$source_sha" "$source_sha" "$upstream_sha" >"$duplicate/usr/lib/xodus/build-info"
expect_reject duplicate "$duplicate" 'installed build-info provenance schema invalid'

unknown=$(make_root unknown)
printf 'XODUS_SOURCE_COMMIT=%s\nXODUS_UPSTREAM_COMMIT=%s\nXODUS_BUILD_CHANNEL=x1\n' "$source_sha" "$upstream_sha" >"$unknown/usr/lib/xodus/build-info"
expect_reject unknown "$unknown" 'installed build-info contains unexpected provenance fields'

echo 'Installed build provenance contract passed.'

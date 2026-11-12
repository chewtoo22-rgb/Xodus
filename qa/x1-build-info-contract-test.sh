#!/usr/bin/env bash
set -euo pipefail
probe=qa/x1-build-info-contract.sh
bash -n "$probe"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/usr/lib/xodus"
source_sha=0123456789abcdef0123456789abcdef01234567
upstream_sha=89abcdef0123456789abcdef0123456789abcdef
cat > "$tmp/usr/lib/xodus/build-info" <<EOF
XODUS_SOURCE_COMMIT=$source_sha
XODUS_UPSTREAM_COMMIT=$upstream_sha
EOF
out=$(XODUS_EXPECTED_SOURCE_COMMIT="$source_sha" bash "$probe" "$tmp")
grep -Fxq 'x1_build_info=pass' <<<"$out"
grep -Fxq "candidate_sha=$source_sha" <<<"$out"
grep -Fxq 'hardware_validation_claim=false' <<<"$out"

if XODUS_EXPECTED_SOURCE_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa bash "$probe" "$tmp" >/dev/null 2>&1; then
  echo 'expected candidate mismatch to fail' >&2; exit 1
fi
printf 'XODUS_SOURCE_COMMIT=%s\nXODUS_SOURCE_COMMIT=%s\nXODUS_UPSTREAM_COMMIT=%s\n' "$source_sha" "$source_sha" "$upstream_sha" > "$tmp/usr/lib/xodus/build-info"
if XODUS_EXPECTED_SOURCE_COMMIT="$source_sha" bash "$probe" "$tmp" >/dev/null 2>&1; then
  echo 'expected duplicate provenance to fail' >&2; exit 1
fi
rm "$tmp/usr/lib/xodus/build-info"
printf 'XODUS_SOURCE_COMMIT=%s\nXODUS_UPSTREAM_COMMIT=%s\n' "$source_sha" "$upstream_sha" > "$tmp/real-info"
ln -s "$tmp/real-info" "$tmp/usr/lib/xodus/build-info"
if XODUS_EXPECTED_SOURCE_COMMIT="$source_sha" bash "$probe" "$tmp" >/dev/null 2>&1; then
  echo 'expected symlink provenance to fail' >&2; exit 1
fi
echo 'x1 installed build-info contract: PASS'

#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
collector="$repo_root/qa/hardware-live-evidence.sh"
overlay="$repo_root/overlay/apply-xodus-identity.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

sha_env="0123456789abcdef0123456789abcdef01234567"
sha_manifest="89abcdef0123456789abcdef0123456789abcdef"
sha_build="fedcba9876543210fedcba9876543210fedcba98"

XODUS_CANDIDATE_SHA="$sha_env" bash "$collector" "$tmp/env-evidence" >/dev/null
grep -Fqx "candidate_sha=$sha_env" "$tmp/env-evidence/summary.txt"
grep -Fqx 'candidate_sha_source=environment' "$tmp/env-evidence/summary.txt"
grep -Fqx 'hardware_validation_claim=false' "$tmp/env-evidence/summary.txt"
grep -Fqx 'collector=pass' "$tmp/env-evidence/summary.txt"
test -s "$tmp/env-evidence/lsblk.txt"
test -s "$tmp/env-evidence/uname.txt"

cat >"$tmp/hardware-candidate.json" <<EOF
{
  "schema": 1,
  "candidate_sha": "$sha_manifest",
  "policy": "live-boot-only-until-destructive-installer-vm-gate-passes"
}
EOF
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST="$tmp/hardware-candidate.json" XODUS_BUILD_INFO="$tmp/missing-build-info" \
  bash "$collector" "$tmp/manifest-evidence" >/dev/null
grep -Fqx "candidate_sha=$sha_manifest" "$tmp/manifest-evidence/summary.txt"
grep -Fqx 'candidate_sha_source=manifest' "$tmp/manifest-evidence/summary.txt"

# A produced Xodus payload must be sufficient to establish candidate provenance
# without a Git checkout or network-side qualification manifest.
cat >"$tmp/build-info" <<EOF
XODUS_NAME=Xodus
XODUS_CHANNEL=M0-First-Blood
XODUS_FOUNDATION=pearOS-NiceC0re
XODUS_SOURCE_COMMIT=$sha_build
XODUS_UPSTREAM_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
EOF
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST= XODUS_BUILD_INFO="$tmp/build-info" \
  bash "$collector" "$tmp/build-info-evidence" >/dev/null
grep -Fqx "candidate_sha=$sha_build" "$tmp/build-info-evidence/summary.txt"
grep -Fqx 'candidate_sha_source=build-info' "$tmp/build-info-evidence/summary.txt"

# Invalid or substituted build provenance must fail closed before evidence is
# published. Do not silently fall back to a nearby checkout once payload
# provenance exists but cannot be trusted.
cat >"$tmp/bad-build-info" <<'EOF'
XODUS_SOURCE_COMMIT=not-a-sha
EOF
set +e
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST= XODUS_BUILD_INFO="$tmp/bad-build-info" \
  bash "$collector" "$tmp/bad-build-evidence" >/dev/null 2>"$tmp/bad-build.err"
rc=$?
set -e
[[ "$rc" -eq 3 ]]
grep -Fq 'Xodus build-info must contain exactly one valid XODUS_SOURCE_COMMIT' "$tmp/bad-build.err"
[[ ! -e "$tmp/bad-build-evidence" ]]

ln -s "$tmp/build-info" "$tmp/build-info-link"
set +e
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST= XODUS_BUILD_INFO="$tmp/build-info-link" \
  bash "$collector" "$tmp/symlink-build-evidence" >/dev/null 2>"$tmp/symlink-build.err"
rc=$?
set -e
[[ "$rc" -eq 3 ]]
[[ ! -e "$tmp/symlink-build-evidence" ]]

# The ISO overlay must carry the exact collector into the live filesystem and
# assert its executable presence as part of overlay success.
grep -Fq 'hardware_evidence_source="$repo_root/qa/hardware-live-evidence.sh"' "$overlay"
grep -Fq 'install -Dm0755 "$hardware_evidence_source" "$root/pear/airootfs/usr/lib/xodus/xodus-hardware-live-evidence"' "$overlay"
grep -Fq 'test -x "$root/pear/airootfs/usr/lib/xodus/xodus-hardware-live-evidence"' "$overlay"

# Malformed manifest provenance must fail before publishing any evidence directory.
cat >"$tmp/bad-candidate.json" <<'EOF'
{"schema":1,"candidate_sha":"not-a-sha"}
EOF
set +e
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST="$tmp/bad-candidate.json" XODUS_BUILD_INFO="$tmp/missing-build-info" \
  bash "$collector" "$tmp/bad-evidence" >/dev/null 2>"$tmp/bad.err"
rc=$?
set -e
[[ "$rc" -eq 3 ]]
grep -Fq 'candidate manifest must contain exactly one valid 40-character candidate_sha' "$tmp/bad.err"
[[ ! -e "$tmp/bad-evidence" ]]

# Duplicate provenance is ambiguous and must fail closed.
cat >"$tmp/duplicate-candidate.json" <<EOF
{"candidate_sha":"$sha_env","nested":{"candidate_sha":"$sha_manifest"}}
EOF
set +e
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST="$tmp/duplicate-candidate.json" XODUS_BUILD_INFO="$tmp/missing-build-info" \
  bash "$collector" "$tmp/duplicate-evidence" >/dev/null 2>"$tmp/duplicate.err"
rc=$?
set -e
[[ "$rc" -eq 3 ]]
[[ ! -e "$tmp/duplicate-evidence" ]]

# Symlinked manifests are rejected rather than followed.
ln -s "$tmp/hardware-candidate.json" "$tmp/manifest-link.json"
set +e
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST="$tmp/manifest-link.json" XODUS_BUILD_INFO="$tmp/missing-build-info" \
  bash "$collector" "$tmp/symlink-manifest-evidence" >/dev/null 2>"$tmp/symlink-manifest.err"
rc=$?
set -e
[[ "$rc" -eq 3 ]]
[[ ! -e "$tmp/symlink-manifest-evidence" ]]

# Existing destinations, including symlinks, must never be merged or overwritten.
mkdir "$tmp/existing-evidence"
printf 'sentinel\n' >"$tmp/existing-evidence/keep.txt"
set +e
XODUS_CANDIDATE_SHA="$sha_env" bash "$collector" "$tmp/existing-evidence" >/dev/null 2>"$tmp/existing.err"
rc=$?
set -e
[[ "$rc" -eq 4 ]]
grep -Fqx 'sentinel' "$tmp/existing-evidence/keep.txt"

mkdir "$tmp/symlink-target"
ln -s "$tmp/symlink-target" "$tmp/evidence-link"
set +e
XODUS_CANDIDATE_SHA="$sha_env" bash "$collector" "$tmp/evidence-link" >/dev/null 2>"$tmp/symlink.err"
rc=$?
set -e
[[ "$rc" -eq 4 ]]
[[ ! -e "$tmp/symlink-target/summary.txt" ]]

# A failed provenance check must not leave staging directories behind.
if compgen -G "$tmp/.xodus-hardware-evidence.*" >/dev/null; then
  printf 'unexpected staging evidence directory remains after failure\n' >&2
  exit 1
fi

printf 'hardware-live-evidence hardening contract: PASS\n'

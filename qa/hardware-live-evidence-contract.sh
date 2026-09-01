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
{"schema":1,"candidate_sha":"$sha_manifest"}
EOF
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST="$tmp/hardware-candidate.json" XODUS_BUILD_INFO="$tmp/missing-build-info" bash "$collector" "$tmp/manifest-evidence" >/dev/null
grep -Fqx "candidate_sha=$sha_manifest" "$tmp/manifest-evidence/summary.txt"
cat >"$tmp/build-info" <<EOF
XODUS_SOURCE_COMMIT=$sha_build
XODUS_UPSTREAM_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
EOF
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST= XODUS_BUILD_INFO="$tmp/build-info" bash "$collector" "$tmp/build-info-evidence" >/dev/null
grep -Fqx "candidate_sha=$sha_build" "$tmp/build-info-evidence/summary.txt"
grep -Fqx 'candidate_sha_source=build-info' "$tmp/build-info-evidence/summary.txt"
cat >"$tmp/bad-build-info" <<'EOF'
XODUS_SOURCE_COMMIT=not-a-sha
EOF
set +e
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST= XODUS_BUILD_INFO="$tmp/bad-build-info" bash "$collector" "$tmp/bad-build-evidence" >/dev/null 2>"$tmp/bad-build.err"
rc=$?
set -e
[[ "$rc" -eq 3 && ! -e "$tmp/bad-build-evidence" ]]
ln -s "$tmp/build-info" "$tmp/build-info-link"
set +e
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST= XODUS_BUILD_INFO="$tmp/build-info-link" bash "$collector" "$tmp/symlink-build-evidence" >/dev/null 2>/dev/null
rc=$?
set -e
[[ "$rc" -eq 3 && ! -e "$tmp/symlink-build-evidence" ]]
grep -Fq 'hardware_evidence_source="$repo_root/qa/hardware-live-evidence.sh"' "$overlay"
grep -Fq 'xodus-hardware-live-evidence' "$overlay"
mkdir "$tmp/existing-evidence"
printf 'sentinel\n' >"$tmp/existing-evidence/keep.txt"
set +e
XODUS_CANDIDATE_SHA="$sha_env" bash "$collector" "$tmp/existing-evidence" >/dev/null 2>/dev/null
rc=$?
set -e
[[ "$rc" -eq 4 ]]
grep -Fqx sentinel "$tmp/existing-evidence/keep.txt"
mkdir "$tmp/symlink-target"
ln -s "$tmp/symlink-target" "$tmp/evidence-link"
set +e
XODUS_CANDIDATE_SHA="$sha_env" bash "$collector" "$tmp/evidence-link" >/dev/null 2>/dev/null
rc=$?
set -e
[[ "$rc" -eq 4 && ! -e "$tmp/symlink-target/summary.txt" ]]
# The parent itself may look ordinary while an ancestor component redirects it.
# Evidence must stay in the operator-selected path, so reject this ambiguity.
mkdir -p "$tmp/real-parent/nested"
ln -s "$tmp/real-parent" "$tmp/linked-parent"
set +e
XODUS_CANDIDATE_SHA="$sha_env" bash "$collector" "$tmp/linked-parent/nested/evidence" >/dev/null 2>"$tmp/nested-parent.err"
rc=$?
set -e
[[ "$rc" -eq 4 ]]
grep -Fq 'parent traverses a symlink' "$tmp/nested-parent.err"
[[ ! -e "$tmp/real-parent/nested/evidence" ]]
if compgen -G "$tmp/.xodus-hardware-evidence.*" >/dev/null; then exit 1; fi
printf 'hardware-live-evidence hardening contract: PASS\n'

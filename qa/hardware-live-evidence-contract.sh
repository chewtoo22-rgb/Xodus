#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
collector="$repo_root/qa/hardware-live-evidence.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

sha_env="0123456789abcdef0123456789abcdef01234567"
sha_manifest="89abcdef0123456789abcdef0123456789abcdef"

XODUS_CANDIDATE_SHA="$sha_env" bash "$collector" "$tmp/env-evidence" >/dev/null
grep -Fqx "candidate_sha=$sha_env" "$tmp/env-evidence/summary.txt"
grep -Fqx 'candidate_sha_source=environment' "$tmp/env-evidence/summary.txt"
grep -Fqx 'collector=pass' "$tmp/env-evidence/summary.txt"

cat >"$tmp/hardware-candidate.json" <<EOF
{
  "schema": 1,
  "candidate_sha": "$sha_manifest",
  "policy": "live-boot-only-until-destructive-installer-vm-gate-passes"
}
EOF
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST="$tmp/hardware-candidate.json" \
  bash "$collector" "$tmp/manifest-evidence" >/dev/null
grep -Fqx "candidate_sha=$sha_manifest" "$tmp/manifest-evidence/summary.txt"
grep -Fqx 'candidate_sha_source=manifest' "$tmp/manifest-evidence/summary.txt"

cat >"$tmp/bad-candidate.json" <<'EOF'
{"schema":1,"candidate_sha":"not-a-sha"}
EOF
set +e
XODUS_CANDIDATE_SHA= XODUS_CANDIDATE_MANIFEST="$tmp/bad-candidate.json" \
  bash "$collector" "$tmp/bad-evidence" >/dev/null 2>"$tmp/bad.err"
rc=$?
set -e
[[ "$rc" -eq 3 ]]
grep -Fq 'unable to resolve a valid 40-character Xodus candidate SHA' "$tmp/bad.err"
[[ ! -e "$tmp/bad-evidence/summary.txt" ]]

printf 'hardware-live-evidence provenance contract: PASS\n'
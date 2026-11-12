#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
overlay="$repo_root/overlay/apply-xodus-identity.sh"
unit="$repo_root/overlay/first-boot/xodus-ai-runtime-preflight.service"
runtime="$repo_root/scripts/xodus-ai-runtime-preflight.py"

fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -f "$overlay" ]] || fail "missing identity overlay"
[[ -f "$unit" ]] || fail "missing runtime preflight unit"
[[ -f "$runtime" ]] || fail "missing runtime preflight implementation"

# The payload must carry the exact implementation and unit that exist in the
# repository, and the service must be enabled in the same multi-user target as
# the hardware-selection service it follows.
grep -Fq 'runtime_preflight_source="$repo_root/scripts/xodus-ai-runtime-preflight.py"' "$overlay" || fail "runtime implementation is not sourced from repository"
grep -Fq 'runtime_preflight_unit="$script_dir/first-boot/xodus-ai-runtime-preflight.service"' "$overlay" || fail "runtime unit is not sourced from repository"
grep -Fq 'install -Dm0755 "$runtime_preflight_source" "$root/pear/airootfs/usr/lib/xodus/xodus-ai-runtime-preflight.py"' "$overlay" || fail "runtime implementation is not installed into payload"
grep -Fq 'install -Dm0644 "$runtime_preflight_unit" "$root/pear/airootfs/usr/lib/systemd/system/xodus-ai-runtime-preflight.service"' "$overlay" || fail "runtime unit is not installed into payload"
grep -Fq 'multi-user.target.wants/xodus-ai-runtime-preflight.service' "$overlay" || fail "runtime service is not enabled"
grep -Fq 'test -x "$root/pear/airootfs/usr/lib/xodus/xodus-ai-runtime-preflight.py"' "$overlay" || fail "payload assertion missing runtime executable"
grep -Fq 'test -L "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-ai-runtime-preflight.service"' "$overlay" || fail "payload assertion missing enabled service"

# Keep the service chained behind hardware selection and fail closed unless the
# durable selection record exists. Its ExecStart must reference the payload path
# installed above rather than a repository/build-host path.
grep -Fxq 'After=xodus-ai-first-boot.service' "$unit" || fail "runtime service ordering drifted"
grep -Fxq 'Requires=xodus-ai-first-boot.service' "$unit" || fail "runtime service dependency drifted"
grep -Fxq 'ConditionPathExists=/var/lib/xodus/ai/hardware-selection.json' "$unit" || fail "runtime hardware-state gate drifted"
grep -Fxq 'ExecStart=/usr/bin/python3 /usr/lib/xodus/xodus-ai-runtime-preflight.py --output /var/lib/xodus/ai/runtime-readiness.json' "$unit" || fail "runtime ExecStart does not consume installed payload"

# The implementation remains a preflight only. Downloads and service launch
# belong to a later explicit runtime manager, not first boot.
if grep -Eq 'subprocess\.|os\.system\(|requests\.|urllib\.|curl |wget ' "$runtime"; then
  fail "runtime preflight gained execution/network primitives"
fi

echo "PASS: AI runtime overlay installation contract"

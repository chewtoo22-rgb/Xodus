#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
prepare="$repo_root/scripts/prepare-qualified-installer.sh"

bash -n "$prepare"
python3 -m py_compile "$repo_root/scripts/patch-installer-xodus-payload.py"

grep -Fq 'audit-installer-driver.sh' "$prepare"
grep -Fq 'patch-installer-xodus-payload.py' "$prepare"
grep -Fq 'sha256sum "$setup" "$prepared"' "$prepare"
grep -Fq 'qualification=audited-upstream-plus-xodus-payload-handoff' "$prepare"

# Safety contract: this composition layer prepares installer text only. It must
# never acquire destructive disk primitives of its own.
if grep -En '(^|[[:space:]])(mkfs|wipefs|sgdisk|parted|fdisk|losetup|qemu-system|dd)([[:space:]]|$)' "$prepare"; then
  echo 'ERROR: qualified installer preparation gained destructive primitives' >&2
  exit 1
fi

# Ensure preparation remains fail-closed rather than silently tolerating a
# missing handoff in the generated installer.
grep -Fq 'ERROR: first-boot payload handoff absent' "$prepare"
grep -Fq 'ERROR: first-boot enablement absent' "$prepare"
grep -Fq 'ERROR: AI first-boot payload handoff absent' "$prepare"

echo 'qualified installer preparation contract: PASS'

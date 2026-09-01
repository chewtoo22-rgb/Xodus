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

# Qualification evidence is append-only by directory. The preparation step
# must not recursively clean prior output and must fail before invoking the
# upstream audit when the destination is unsafe.
if grep -Fq 'rm -rf' "$prepare"; then
  echo 'ERROR: qualified installer preparation may recursively delete evidence' >&2
  exit 1
fi
grep -Fq 'qualified installer output already exists; refusing to overwrite evidence' "$prepare"
grep -Fq 'qualified installer output parent traverses a symlink' "$prepare"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

existing="$tmp/existing"
mkdir "$existing"
if bash "$prepare" "$repo_root/upstream/installer.lock" "$existing" >"$tmp/existing.out" 2>"$tmp/existing.err"; then
  echo 'ERROR: preparation accepted an existing output directory' >&2
  exit 1
fi
grep -Fq 'refusing to overwrite evidence' "$tmp/existing.err"

mkdir "$tmp/real-parent"
ln -s "$tmp/real-parent" "$tmp/linked-parent"
if bash "$prepare" "$repo_root/upstream/installer.lock" "$tmp/linked-parent/new-output" >"$tmp/symlink.out" 2>"$tmp/symlink.err"; then
  echo 'ERROR: preparation accepted a symlinked output parent' >&2
  exit 1
fi
grep -Fq 'output parent traverses a symlink' "$tmp/symlink.err"

ln -s "$tmp/missing-target" "$tmp/output-link"
if bash "$prepare" "$repo_root/upstream/installer.lock" "$tmp/output-link" >"$tmp/link.out" 2>"$tmp/link.err"; then
  echo 'ERROR: preparation accepted a symlink output destination' >&2
  exit 1
fi
grep -Fq 'refusing to overwrite evidence' "$tmp/link.err"

# Ensure preparation remains fail-closed rather than silently tolerating a
# missing handoff in the generated installer.
grep -Fq 'ERROR: first-boot payload handoff absent' "$prepare"
grep -Fq 'ERROR: first-boot enablement absent' "$prepare"
grep -Fq 'ERROR: AI first-boot payload handoff absent' "$prepare"

echo 'qualified installer preparation contract: PASS'

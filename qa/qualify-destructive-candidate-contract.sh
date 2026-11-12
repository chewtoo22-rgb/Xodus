#!/usr/bin/env bash
set -euo pipefail

script=qa/qualify-destructive-candidate.sh
[[ -f "$script" ]]
bash -n "$script"

grep -q 'XODUS_CANDIDATE_SHA' "$script"
grep -q 'sha256sum.*ISO_PATH' "$script"
grep -q 'cat-file -e' "$script"
grep -q 'installer-vm-destructive.sh' "$script"
grep -q 'destructive_vm_install_gate=pass' "$script"
grep -q 'post_install_uefi_userspace=pass' "$script"
grep -q 'physical_hardware_validation=not_claimed' "$script"

# Qualification must delegate destructive behavior to the already guarded VM
# gate. Reject partitioning/formatting primitives in this provenance wrapper.
if grep -Ev '^[[:space:]]*(#|$)' "$script" | grep -Eiq '(^|[;&|[:space:]])(mkfs(\.|[[:space:]])|wipefs([[:space:]]|$)|sgdisk([[:space:]]|$)|parted([[:space:]]|$)|fdisk([[:space:]]|$)|dd[[:space:]].*of=/dev/)'; then
  echo 'ERROR: destructive primitive found in provenance wrapper' >&2
  exit 1
fi

printf 'destructive candidate provenance contract: PASS\n'

#!/usr/bin/env bash
set -euo pipefail
script=qa/x1-nuc-preflight.sh
[[ -f "$script" ]]
bash -n "$script"

# The preflight is intentionally read-only. Reject destructive primitives in
# executable lines while allowing their names in comments/messages.
if grep -Ev '^[[:space:]]*(#|$)' "$script" | grep -Eiq '(^|[;&|[:space:]])(mkfs(\.|[[:space:]])|wipefs([[:space:]]|$)|sgdisk([[:space:]]|$)|parted([[:space:]]|$)|fdisk([[:space:]]|$)|dd[[:space:]].*of=/dev/|mount([[:space:]]|$)|umount([[:space:]]|$)|reboot([[:space:]]|$)|poweroff([[:space:]]|$))'; then
  echo 'destructive command found in X1 NUC preflight' >&2
  exit 1
fi

grep -q '/sys/firmware/efi' "$script"
grep -q 'findmnt' "$script"
grep -q 'lsblk' "$script"
grep -q 'XODUS_CANDIDATE_SHA' "$script"
grep -q 'XODUS_EXPECTED_SOURCE_COMMIT' "$script"
grep -q 'x1-build-info-contract.sh' "$script"
grep -q 'live system provenance matches qualified candidate' "$script"
grep -q 'systemd-detect-virt' "$script"
grep -q 'physical X1 NUC evidence is required' "$script"
grep -q 'virtualization=%s' "$script"
grep -q 'SUMMARY candidate_sha=' "$script"
grep -q 'destructive_actions=0' "$script"
printf 'X1 NUC preflight contract: PASS\n'

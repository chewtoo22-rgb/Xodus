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
grep -q 'destructive_actions=0' "$script"
printf 'X1 NUC preflight contract: PASS\n'

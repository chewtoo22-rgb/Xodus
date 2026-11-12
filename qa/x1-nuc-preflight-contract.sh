#!/usr/bin/env bash
set -euo pipefail
script=qa/x1-nuc-preflight.sh
overlay=overlay/apply-xodus-identity.sh
[[ -f "$script" ]]
[[ -f "$overlay" ]]
bash -n "$script"
bash -n "$overlay"

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
grep -q '/usr/lib/xodus/xodus-build-info-verify' "$script"
grep -q 'x1-build-info-contract.sh' "$script"
grep -q 'live system provenance matches qualified candidate' "$script"
grep -q 'systemd-detect-virt' "$script"
grep -q 'physical X1 NUC evidence is required' "$script"
grep -q 'systemd-detect-virt unavailable; physical X1 NUC evidence cannot be verified' "$script"
grep -q 'systemd-detect-virt returned no trustworthy result; physical X1 NUC evidence cannot be verified' "$script"
if grep -q 'systemd-detect-virt unavailable; physical-machine boundary could not be verified' "$script"; then
  echo 'physical-machine boundary must fail closed when virtualization detection is unavailable' >&2
  exit 1
fi
grep -q 'virtualization=%s' "$script"
grep -q 'SUMMARY candidate_sha=' "$script"
grep -q 'destructive_actions=0' "$script"

# The production ISO must carry both the preflight and its build-info verifier.
# This prevents physical qualification from depending on a Git checkout or
# network access after booting the candidate media.
grep -Fq 'qa/x1-nuc-preflight.sh' "$overlay"
grep -Fq 'qa/x1-build-info-contract.sh' "$overlay"
grep -Fq 'usr/lib/xodus/xodus-x1-nuc-preflight' "$overlay"
grep -Fq 'usr/lib/xodus/xodus-build-info-verify' "$overlay"
grep -Fq 'install -Dm0755 "$nuc_preflight_source"' "$overlay"
grep -Fq 'install -Dm0755 "$build_info_verifier_source"' "$overlay"
grep -Fq 'test -x "$root/pear/airootfs/usr/lib/xodus/xodus-x1-nuc-preflight"' "$overlay"
grep -Fq 'test -x "$root/pear/airootfs/usr/lib/xodus/xodus-build-info-verify"' "$overlay"

printf 'X1 NUC preflight contract: PASS\n'

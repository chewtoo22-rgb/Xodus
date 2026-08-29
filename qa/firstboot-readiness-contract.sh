#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/pear/airootfs"

bash -n "$repo/overlay/apply-xodus-firstboot.sh"
bash "$repo/overlay/apply-xodus-firstboot.sh" "$tmp"
runtime="$tmp/pear/airootfs/usr/lib/xodus/xodus-firstboot-readiness"
unit="$tmp/pear/airootfs/usr/lib/systemd/system/xodus-firstboot-readiness.service"
link="$tmp/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-firstboot-readiness.service"

test -x "$runtime"
grep -Fq 'ConditionPathExists=!/var/lib/xodus/firstboot/readiness.env' "$unit"
test "$(readlink "$link")" = /usr/lib/systemd/system/xodus-firstboot-readiness.service

state="$tmp/state"
XODUS_FIRSTBOOT_STATE_DIR="$state" XODUS_TEST_ROOT_SOURCE=/dev/nvme0n1p2 XODUS_TEST_ROOT_FSTYPE=ext4 XODUS_TEST_UEFI=1 XODUS_TEST_SOUND=1 bash "$runtime"
grep -Fq 'XODUS_FIRSTBOOT_SCHEMA=1' "$state/readiness.env"
grep -Fq 'XODUS_INSTALLED_ROOT_SOURCE=/dev/nvme0n1p2' "$state/readiness.env"
grep -Fq 'XODUS_INSTALLED_ROOT_FSTYPE=ext4' "$state/readiness.env"
grep -Fq 'XODUS_UEFI=1' "$state/readiness.env"
grep -Fq 'XODUS_SOUND_PRESENT=1' "$state/readiness.env"
grep -Fq 'XODUS_FIRSTBOOT_COMPLETE=1' "$state/readiness.env"

set +e
XODUS_FIRSTBOOT_STATE_DIR="$tmp/live" XODUS_TEST_ROOT_SOURCE=overlay XODUS_TEST_ROOT_FSTYPE=overlay bash "$runtime" >/dev/null 2>&1
rc=$?
set -e
test "$rc" -eq 78
test ! -e "$tmp/live/readiness.env"

echo 'firstboot readiness contract: PASS'

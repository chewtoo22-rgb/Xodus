#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
collector="$repo_root/qa/hardware-installed-evidence.sh"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

[[ -x "$collector" ]] || fail "collector is not executable: $collector"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

run_expect_rc() {
  local expected="$1" name="$2" source="$3" fstype="$4"
  local out="$tmp/$name"
  set +e
  XODUS_CONTRACT_ROOT_SOURCE="$source" \
  XODUS_CONTRACT_ROOT_FSTYPE="$fstype" \
  XODUS_CONTRACT_ALLOW_NO_EFI=1 \
    "$collector" "$out" >"$tmp/$name.stdout" 2>"$tmp/$name.stderr"
  local rc=$?
  set -e
  [[ "$rc" -eq "$expected" ]] || {
    cat "$tmp/$name.stderr" >&2 || true
    fail "$name returned $rc, expected $expected"
  }
}

# Live-media and ephemeral roots must never be accepted as installed-system evidence.
run_expect_rc 40 overlay-source overlay ext4
run_expect_rc 40 overlay-fstype /dev/sda2 overlay
run_expect_rc 40 squashfs-root /dev/loop0 squashfs
run_expect_rc 40 airootfs-root airootfs ext4
run_expect_rc 40 tmpfs-root tmpfs tmpfs

# A normal block-backed root may proceed when the UEFI gate is explicitly bypassed
# for contract testing. Individual diagnostic commands are intentionally best-effort.
installed="$tmp/installed"
XODUS_CONTRACT_ROOT_SOURCE=/dev/sda2 \
XODUS_CONTRACT_ROOT_FSTYPE=ext4 \
XODUS_CONTRACT_ALLOW_NO_EFI=1 \
  "$collector" "$installed" >/dev/null

grep -qx 'root_source=/dev/sda2' "$installed/summary.txt" || fail 'root source missing from summary'
grep -qx 'root_fstype=ext4' "$installed/summary.txt" || fail 'root fstype missing from summary'
grep -qx 'collector=pass' "$installed/summary.txt" || fail 'collector pass marker missing'
grep -qx 'physical_install_claim=not_automatic' "$installed/summary.txt" || fail 'physical claim guard missing'

printf 'hardware-installed-evidence contract: PASS\n'

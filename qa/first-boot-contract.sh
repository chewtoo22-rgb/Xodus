#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
runner="$repo_root/overlay/first-boot/xodus-first-boot"
unit="$repo_root/overlay/first-boot/xodus-first-boot.service"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

fake_bin="$tmp/bin"
mkdir -p "$fake_bin"
cat > "$fake_bin/findmnt" <<'EOF_FINDMNT'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  *' -o SOURCE '*) printf '%s\n' "${XODUS_TEST_ROOT_SOURCE:-/dev/nvme0n1p2}" ;;
  *' -o FSTYPE '*) printf '%s\n' "${XODUS_TEST_ROOT_FSTYPE:-ext4}" ;;
  *) exit 2 ;;
esac
EOF_FINDMNT
chmod +x "$fake_bin/findmnt"

new_root() {
  local name=$1
  local root="$tmp/$name"
  mkdir -p "$root/etc" "$root/usr/lib/xodus" "$root/sys/firmware/efi"
  printf '0123456789abcdef0123456789abcdef\n' > "$root/etc/machine-id"
  printf 'XODUS_UPSTREAM_COMMIT=0123456789abcdef0123456789abcdef01234567\n' > "$root/usr/lib/xodus/build-info"
  printf '%s\n' "$root"
}

installed=$(new_root installed)
PATH="$fake_bin:$PATH" XODUS_FIRST_BOOT_ROOT="$installed" \
  XODUS_TEST_ROOT_SOURCE=/dev/nvme0n1p2 XODUS_TEST_ROOT_FSTYPE=ext4 \
  bash "$runner"

test -f "$installed/var/lib/xodus/first-boot/complete"
grep -Fxq 'XODUS_FIRST_BOOT_SCHEMA=1' "$installed/var/lib/xodus/first-boot/system.env"
grep -Fxq 'XODUS_ROOT_SOURCE=/dev/nvme0n1p2' "$installed/var/lib/xodus/first-boot/system.env"
grep -Fxq 'XODUS_ROOT_FSTYPE=ext4' "$installed/var/lib/xodus/first-boot/system.env"
grep -Fxq 'XODUS_FIRMWARE=uefi' "$installed/var/lib/xodus/first-boot/system.env"
grep -Fxq 'XODUS_UPSTREAM_COMMIT=0123456789abcdef0123456789abcdef01234567' "$installed/var/lib/xodus/first-boot/system.env"

before=$(sha256sum "$installed/var/lib/xodus/first-boot/system.env" | awk '{print $1}')
PATH="$fake_bin:$PATH" XODUS_FIRST_BOOT_ROOT="$installed" \
  XODUS_TEST_ROOT_SOURCE=airootfs XODUS_TEST_ROOT_FSTYPE=overlay \
  bash "$runner"
after=$(sha256sum "$installed/var/lib/xodus/first-boot/system.env" | awk '{print $1}')
test "$before" = "$after"

live=$(new_root live)
PATH="$fake_bin:$PATH" XODUS_FIRST_BOOT_ROOT="$live" \
  XODUS_TEST_ROOT_SOURCE=airootfs XODUS_TEST_ROOT_FSTYPE=overlay \
  bash "$runner"
test ! -e "$live/var/lib/xodus/first-boot/complete"

missing_id=$(new_root missing-id)
: > "$missing_id/etc/machine-id"
if PATH="$fake_bin:$PATH" XODUS_FIRST_BOOT_ROOT="$missing_id" \
  XODUS_TEST_ROOT_SOURCE=/dev/sda2 XODUS_TEST_ROOT_FSTYPE=ext4 \
  bash "$runner"; then
  echo 'expected missing machine-id to fail closed' >&2
  exit 1
fi
test ! -e "$missing_id/var/lib/xodus/first-boot/complete"

bad_provenance=$(new_root bad-provenance)
printf 'XODUS_UPSTREAM_COMMIT=not-a-sha\n' > "$bad_provenance/usr/lib/xodus/build-info"
PATH="$fake_bin:$PATH" XODUS_FIRST_BOOT_ROOT="$bad_provenance" \
  XODUS_TEST_ROOT_SOURCE=/dev/sda2 XODUS_TEST_ROOT_FSTYPE=btrfs \
  bash "$runner"
grep -Fxq 'XODUS_UPSTREAM_COMMIT=unknown' "$bad_provenance/var/lib/xodus/first-boot/system.env"

grep -Fxq 'ConditionPathExists=!/var/lib/xodus/first-boot/complete' "$unit"
grep -Fxq 'ExecStart=/usr/lib/xodus/xodus-first-boot' "$unit"
grep -Fxq 'ReadWritePaths=/var/lib/xodus/first-boot' "$unit"
grep -Fxq 'WantedBy=multi-user.target' "$unit"

echo 'first-boot contract: PASS'

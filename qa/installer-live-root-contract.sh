#!/usr/bin/env bash
set -euo pipefail

iso="${1:-}"
outdir="${2:-qa-installer-live-root-artifacts}"

if [[ -z "$iso" || ! -f "$iso" ]]; then
  echo "usage: $0 <qualified-xodus.iso> [evidence-dir]" >&2
  exit 2
fi

for cmd in bsdtar unsquashfs git sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing required command: $cmd" >&2; exit 69; }
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
lock="$repo_root/upstream/installer.lock"
[[ -f "$lock" ]] || { echo "ERROR: installer lock missing" >&2; exit 66; }

# shellcheck disable=SC1090
source "$lock"
: "${SETUP_PATH:?installer lock missing SETUP_PATH}"
: "${SETUP_BLOB:?installer lock missing SETUP_BLOB}"
: "${REF:?installer lock missing REF}"

mkdir -p "$outdir"
outdir="$(readlink -f "$outdir")"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

sha256sum "$iso" | tee "$outdir/iso.sha256"

sfs_path="$(bsdtar -tf "$iso" | awk '/(^|\/)airootfs\.sfs$/ {print; exit}')"
if [[ -z "$sfs_path" ]]; then
  echo "ERROR: qualified ISO does not contain airootfs.sfs" >&2
  exit 3
fi
printf 'squashfs_path=%s\n' "$sfs_path" | tee "$outdir/iso-layout.txt"

mkdir -p "$work/iso"
(
  cd "$work/iso"
  bsdtar -xf "$iso" "$sfs_path"
)
sfs="$work/iso/$sfs_path"
[[ -f "$sfs" ]] || { echo "ERROR: failed to extract live root squashfs" >&2; exit 4; }

# Extract only the installer contract surface. This keeps CI disk usage bounded while
# proving the produced ISO, not merely upstream Git, contains the audited driver.
mkdir -p "$work/root"
unsquashfs -no-progress -d "$work/root" "$sfs" \
  usr/share/pearOS-installer/system_install/setup \
  usr/local/bin/bin_install >"$outdir/unsquashfs.txt" 2>&1

embedded_setup="$work/root/usr/share/pearOS-installer/system_install/setup"
embedded_entry="$work/root/usr/local/bin/bin_install"
[[ -f "$embedded_setup" ]] || { echo "ERROR: live ISO is missing embedded installer setup" >&2; exit 5; }
[[ -f "$embedded_entry" ]] || { echo "ERROR: live ISO is missing bin_install entrypoint" >&2; exit 6; }

actual_blob="$(git hash-object "$embedded_setup")"
printf 'expected_blob=%s\nactual_blob=%s\ninstaller_ref=%s\n' \
  "$SETUP_BLOB" "$actual_blob" "$REF" | tee "$outdir/installer-blob.txt"
if [[ "$actual_blob" != "$SETUP_BLOB" ]]; then
  echo "ERROR: qualified ISO installer blob differs from upstream/installer.lock" >&2
  exit 7
fi

if ! grep -Fq 'cd /usr/share/pearOS-installer/system_install/' "$embedded_entry" || \
   ! grep -Eq '(^|[[:space:]])make([[:space:]]|$)' "$embedded_entry"; then
  echo "ERROR: live installer entrypoint no longer invokes the audited system_install tree" >&2
  cat "$embedded_entry" >&2
  exit 8
fi

# Record the destructive primitives present in the exact embedded setup for later
# comparison with the VM execution gate. Do not execute them in this contract test.
grep -nE 'wipefs|sgdisk|parted|mkfs\.|pacstrap|arch-chroot|grub-install|refind' "$embedded_setup" \
  >"$outdir/destructive-primitives.txt" || true

cat >"$outdir/summary.txt" <<EOF
qualified_iso=$(basename "$iso")
installer_ref=$REF
installer_path=/usr/share/pearOS-installer/system_install/setup
installer_blob=$actual_blob
entrypoint=/usr/local/bin/bin_install
live_root_contract=pass
installer_invoked=no
physical_install_policy=locked
EOF

cat "$outdir/summary.txt"
echo "PASS: qualified Xodus ISO embeds the exact pinned pearOS installer driver."

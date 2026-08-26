#!/usr/bin/env bash
set -euo pipefail

iso="${1:-}"
outdir="${2:-qa-installer-live-root-artifacts}"

if [[ -z "$iso" || ! -f "$iso" ]]; then
  echo "usage: $0 <qualified-xodus.iso> [evidence-dir]" >&2
  exit 2
fi

for cmd in unsquashfs git sha256sum mount umount find; do
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

iso="$(readlink -f "$iso")"
mkdir -p "$outdir"
outdir="$(readlink -f "$outdir")"
work="$(mktemp -d)"
iso_mount="$work/iso-mount"
mkdir -p "$iso_mount"
mounted=0
cleanup() {
  if [[ "$mounted" -eq 1 ]]; then
    sudo umount "$iso_mount" >/dev/null 2>&1 || true
  fi
  # unsquashfs preserves ownership metadata from the live image. Some selectively
  # extracted paths can therefore be root-owned on the runner, so cleanup must use
  # the same privilege boundary used for the loop mount. Never let cleanup convert
  # an already-passed installer contract into a false CI failure.
  sudo rm -rf "$work" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sha256sum "$iso" | tee "$outdir/iso.sha256"

# The Xodus image is a hybrid boot ISO. Ubuntu's libarchive/bsdtar cannot reliably
# traverse this image shape, so inspect it through the kernel's ISO9660 loop mount
# instead. Keep the mount read-only and never copy/extract the full live root.
if ! sudo mount -o loop,ro "$iso" "$iso_mount"; then
  echo "ERROR: failed to mount qualified ISO read-only" >&2
  exit 3
fi
mounted=1

sfs="$(find "$iso_mount" -type f -name 'airootfs.sfs' -print -quit)"
if [[ -z "$sfs" ]]; then
  echo "ERROR: qualified ISO does not contain airootfs.sfs" >&2
  find "$iso_mount" -maxdepth 4 -type f -printf '%P\n' | head -n 200 >"$outdir/iso-files.txt" || true
  exit 4
fi
sfs_path="${sfs#"$iso_mount"/}"
printf 'squashfs_path=%s\n' "$sfs_path" | tee "$outdir/iso-layout.txt"

installer_listing="$work/installer-layout.full.txt"
unsquashfs -ll "$sfs" \
  | awk '/pearOS-installer|bin_install|system_install\/setup/ {print}' \
  >"$installer_listing"
head -n 200 "$installer_listing" >"$outdir/installer-layout.txt" || true

setup_rel="$(awk '{p=$NF; sub(/^squashfs-root\//, "", p); if (p ~ /(^|\/)usr\/share\/pearOS-installer\/system_install\/setup$/) {print p; exit}}' "$installer_listing")"
entry_rel="$(awk '{p=$NF; sub(/^squashfs-root\//, "", p); if (p ~ /(^|\/)usr\/local\/bin\/bin_install$/) {print p; exit}}' "$installer_listing")"

if [[ -z "$setup_rel" ]]; then
  echo "ERROR: qualified ISO live root does not contain the pinned installer setup path" >&2
  cat "$outdir/installer-layout.txt" >&2
  exit 5
fi
if [[ -z "$entry_rel" ]]; then
  echo "ERROR: qualified ISO live root does not contain the bin_install entrypoint" >&2
  cat "$outdir/installer-layout.txt" >&2
  exit 6
fi
printf 'setup_rel=%s\nentry_rel=%s\n' "$setup_rel" "$entry_rel" >>"$outdir/iso-layout.txt"

mkdir -p "$work/root"
if ! unsquashfs -no-progress -d "$work/root" "$sfs" "$setup_rel" "$entry_rel" \
  >"$outdir/unsquashfs.txt" 2>&1; then
  echo "ERROR: failed to selectively extract installer contract surface" >&2
  cat "$outdir/unsquashfs.txt" >&2
  exit 7
fi

embedded_setup="$work/root/$setup_rel"
embedded_entry="$work/root/$entry_rel"
[[ -f "$embedded_setup" ]] || { echo "ERROR: extracted live root is missing embedded installer setup" >&2; exit 8; }
[[ -e "$embedded_entry" || -L "$embedded_entry" ]] || { echo "ERROR: extracted live root is missing bin_install entrypoint" >&2; exit 9; }

actual_blob="$(git hash-object "$embedded_setup")"
printf 'expected_blob=%s\nactual_blob=%s\ninstaller_ref=%s\n' \
  "$SETUP_BLOB" "$actual_blob" "$REF" | tee "$outdir/installer-blob.txt"
if [[ "$actual_blob" != "$SETUP_BLOB" ]]; then
  echo "ERROR: qualified ISO installer blob differs from upstream/installer.lock" >&2
  exit 10
fi

if [[ -L "$embedded_entry" ]]; then
  printf 'entrypoint_symlink=%s\n' "$(readlink "$embedded_entry")" | tee "$outdir/entrypoint.txt"
else
  cp "$embedded_entry" "$outdir/entrypoint.txt"
  if ! grep -Fq 'cd /usr/share/pearOS-installer/system_install/' "$embedded_entry" || \
     ! grep -Eq '(^|[[:space:]])make([[:space:]]|$)' "$embedded_entry"; then
    echo "ERROR: live installer entrypoint no longer invokes the audited system_install tree" >&2
    cat "$embedded_entry" >&2
    exit 11
  fi
fi

grep -nE 'wipefs|sgdisk|parted|mkfs\.|pacstrap|arch-chroot|grub-install|refind' "$embedded_setup" \
  >"$outdir/destructive-primitives.txt" || true

cat >"$outdir/summary.txt" <<EOF
qualified_iso=$(basename "$iso")
installer_ref=$REF
installer_path=$setup_rel
installer_blob=$actual_blob
entrypoint=$entry_rel
live_root_contract=pass
installer_invoked=no
physical_install_policy=locked
EOF

cat "$outdir/summary.txt"
echo "PASS: qualified Xodus ISO embeds the exact pinned pearOS installer driver."

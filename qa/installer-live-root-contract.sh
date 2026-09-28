#!/usr/bin/env bash
set -euo pipefail

iso="${1:-}"
outdir="${2:-qa-installer-live-root-artifacts}"

if [[ -z "$iso" || ! -f "$iso" ]]; then
  echo "usage: $0 <qualified-xodus.iso> [evidence-dir]" >&2
  exit 2
fi

for cmd in unsquashfs git sha256sum mount umount find cmp stat; do
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
if [[ -n "${PR_HEAD_SHA:-}" && ! "$PR_HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: PR_HEAD_SHA must be a lowercase 40-character git SHA" >&2
  exit 2
fi

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
  | awk '/pearOS-installer|bin_install|system_install\/setup|xodus-live-desktop-probe|usr\/lib\/xodus\/build-info/ {print}' \
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

# These paths are installed by the Xodus overlay. Extract only the contract
# surface so the check catches mode and service activation errors in the actual
# SquashFS without expanding the full live root on the runner.
probe_rel=usr/lib/xodus/xodus-live-desktop-probe
service_rel=usr/lib/systemd/system/xodus-live-desktop-probe.service
wants_rel=etc/systemd/system/graphical.target.wants/xodus-live-desktop-probe.service
build_info_rel=usr/lib/xodus/build-info
xodus_executables=(
  usr/lib/xodus/xodus-hardware-live-evidence
  usr/lib/xodus/xodus-x1-nuc-preflight
  usr/lib/xodus/xodus-build-info-verify
  usr/lib/xodus/xodus-first-boot
  usr/lib/xodus/xodus-ai-first-boot
  usr/lib/xodus/xodus-ai-runtime-preflight.py
  "$probe_rel"
)
if [[ -f "$repo_root/scripts/xodus-ai-select.py" ]]; then
  xodus_executables+=(usr/lib/xodus/xodus-ai-select.py)
fi
printf 'probe_rel=%s\nservice_rel=%s\nwants_rel=%s\nbuild_info_rel=%s\n' \
  "$probe_rel" "$service_rel" "$wants_rel" "$build_info_rel" >>"$outdir/iso-layout.txt"

mkdir -p "$work/root"
if ! unsquashfs -no-progress -d "$work/root" "$sfs" \
  "$setup_rel" "$entry_rel" "${xodus_executables[@]}" "$service_rel" "$wants_rel" "$build_info_rel" \
  >"$outdir/unsquashfs.txt" 2>&1; then
  echo "ERROR: failed to selectively extract installer and desktop contract surfaces" >&2
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

embedded_probe="$work/root/$probe_rel"
embedded_service="$work/root/$service_rel"
embedded_wants="$work/root/$wants_rel"
embedded_build_info="$work/root/$build_info_rel"
[[ -f "$embedded_probe" ]] || { echo "ERROR: live root is missing Xodus desktop probe" >&2; exit 12; }
[[ -f "$embedded_service" ]] || { echo "ERROR: live root is missing Xodus desktop probe service" >&2; exit 13; }
[[ -L "$embedded_wants" ]] || { echo "ERROR: desktop probe is not enabled for graphical.target" >&2; exit 14; }
[[ -f "$embedded_build_info" ]] || { echo "ERROR: live root is missing Xodus build-info" >&2; exit 15; }

: >"$outdir/executable-modes.txt"
for executable_rel in "${xodus_executables[@]}"; do
  embedded_executable="$work/root/$executable_rel"
  [[ -f "$embedded_executable" ]] || {
    echo "ERROR: live root is missing Xodus executable $executable_rel" >&2
    exit 16
  }
  executable_mode="$(stat -c '%a' "$embedded_executable")"
  printf '%s=%s\n' "$executable_rel" "$executable_mode" >>"$outdir/executable-modes.txt"
  [[ "$executable_mode" == 755 ]] || {
    echo "ERROR: live-root executable $executable_rel has mode $executable_mode, expected 755" >&2
    exit 16
  }
done
probe_mode="$(stat -c '%a' "$embedded_probe")"
cmp -s "$repo_root/overlay/live-desktop/xodus-live-desktop-probe" "$embedded_probe" || {
  echo "ERROR: embedded desktop probe differs from the checked-out Xodus source" >&2
  exit 17
}
cmp -s "$repo_root/overlay/live-desktop/xodus-live-desktop-probe.service" "$embedded_service" || {
  echo "ERROR: embedded desktop probe service differs from the checked-out Xodus source" >&2
  exit 18
}
service_target="$(readlink "$embedded_wants")"
[[ "$service_target" == /usr/lib/systemd/system/xodus-live-desktop-probe.service ]] || {
  echo "ERROR: graphical.target desktop probe symlink has unexpected target: $service_target" >&2
  exit 19
}

source_count="$(grep -c '^XODUS_SOURCE_COMMIT=' "$embedded_build_info" || true)"
installer_count="$(grep -c '^XODUS_INSTALLER_COMMIT=' "$embedded_build_info" || true)"
[[ "$source_count" == 1 && "$installer_count" == 1 ]] || {
  echo 'ERROR: build-info must contain exactly one source and installer commit' >&2
  exit 20
}
source_sha="$(sed -n 's/^XODUS_SOURCE_COMMIT=//p' "$embedded_build_info")"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'ERROR: build-info source SHA is invalid' >&2; exit 21; }
grep -Fxq "XODUS_INSTALLER_COMMIT=$REF" "$embedded_build_info" || {
  echo 'ERROR: live-root installer commit differs from upstream/installer.lock' >&2
  exit 22
}
if [[ -n "${PR_HEAD_SHA:-}" && "$source_sha" != "$PR_HEAD_SHA" ]]; then
  echo "ERROR: live-root source SHA $source_sha differs from PR head $PR_HEAD_SHA" >&2
  exit 23
fi

cat >"$outdir/desktop-payload.txt" <<EOF
probe_path=$probe_rel
probe_mode=$probe_mode
probe_sha256=$(sha256sum "$embedded_probe" | awk '{print $1}')
service_path=$service_rel
service_sha256=$(sha256sum "$embedded_service" | awk '{print $1}')
service_symlink=$service_target
source_commit=$source_sha
installer_commit=$REF
EOF

grep -nE 'wipefs|sgdisk|parted|mkfs\.|pacstrap|arch-chroot|grub-install|refind' "$embedded_setup" \
  >"$outdir/destructive-primitives.txt" || true

cat >"$outdir/summary.txt" <<EOF
qualified_iso=$(basename "$iso")
installer_ref=$REF
installer_path=$setup_rel
installer_blob=$actual_blob
entrypoint=$entry_rel
live_root_contract=pass
desktop_payload_contract=pass
installer_invoked=no
physical_install_policy=locked
EOF

cat "$outdir/summary.txt"
echo "PASS: qualified Xodus ISO embeds the pinned installer and executable desktop probe."

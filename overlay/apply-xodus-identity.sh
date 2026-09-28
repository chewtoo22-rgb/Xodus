#!/usr/bin/env bash
set -euo pipefail

root=${1:-}
if [[ -z "$root" || ! -d "$root/pear/airootfs" || ! -f "$root/pear/profiledef.sh" ]]; then
  echo "usage: $0 <pearOS-iso-source-root>" >&2
  exit 64
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
repo_root=$(cd "$script_dir/.." && pwd -P)
profile="$root/pear/profiledef.sh"
hostname_file="$root/pear/airootfs/etc/hostname"
motd_file="$root/pear/airootfs/etc/motd"
builder="$root/build-binary"
installer_lock="$repo_root/upstream/installer.lock"

xodus_source_commit=${XODUS_SOURCE_COMMIT:-unknown}
if [[ "$xodus_source_commit" != "unknown" && ! "$xodus_source_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "XODUS_SOURCE_COMMIT must be a lowercase 40-character git SHA or 'unknown'" >&2
  exit 65
fi
upstream_commit=${XODUS_UPSTREAM_COMMIT:-unknown}
if [[ "$upstream_commit" != "unknown" && ! "$upstream_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "XODUS_UPSTREAM_COMMIT must be a lowercase 40-character git SHA or 'unknown'" >&2
  exit 65
fi

# The pinned pearOS builder otherwise clones the installer's moving main branch
# while constructing the live root. Parse the lock as data, then replace only
# the audited clone command. A changed builder layout must stop the ISO build.
[[ -f "$builder" && ! -L "$builder" && -f "$installer_lock" ]] || {
  echo "pinned installer builder or lock is missing or unsafe" >&2
  exit 66
}
mapfile -t installer_entries < <(awk 'NF && $1 !~ /^#/ {sub(/\r$/, ""); print}' "$installer_lock")
[[ ${#installer_entries[@]} -eq 5 &&
   "${installer_entries[0]}" == 'REPO=https://github.com/pearOS-archlinux/pearOS-installer.git' &&
   "${installer_entries[2]}" == 'SETUP_PATH=system_install/setup' &&
   "${installer_entries[4]}" == 'POLICY=live-boot-only-until-vm-install-gate-passes' ]] || {
  echo "pinned installer lock layout changed" >&2
  exit 66
}
installer_commit="${installer_entries[1]#REF=}"
installer_setup_blob="${installer_entries[3]#SETUP_BLOB=}"
[[ "${installer_entries[1]}" == "REF=$installer_commit" &&
   "$installer_commit" =~ ^[0-9a-f]{40}$ &&
   "${installer_entries[3]}" == "SETUP_BLOB=$installer_setup_blob" &&
   "$installer_setup_blob" =~ ^[0-9a-f]{40}$ ]] || {
  echo "pinned installer commit or setup blob is invalid" >&2
  exit 66
}
command -v python3 >/dev/null 2>&1 || { echo "python3 is required to pin the installer source" >&2; exit 66; }
python3 - "$builder" "$installer_commit" "$installer_setup_blob" <<'PY'
from pathlib import Path
import sys

builder = Path(sys.argv[1])
commit, setup_blob = sys.argv[2:]
source = builder.read_text()
old = '    git clone --depth 1 https://github.com/pearOS-archlinux/pearOS-installer.git "${pacstrap_dir}/usr/share/pearOS-installer" || _msg_error "Failed to clone pearOS-installer from GitHub" 1'
if source.count(old) != 1 or source.count('    # Clone pearOS-installer from GitHub instead of using local files') != 1:
    raise SystemExit('pinned upstream installer clone layout changed')
new = '''    git init -q "${pacstrap_dir}/usr/share/pearOS-installer" || _msg_error "Failed to initialize pearOS-installer repository" 1
    git -C "${pacstrap_dir}/usr/share/pearOS-installer" remote add origin https://github.com/pearOS-archlinux/pearOS-installer.git || _msg_error "Failed to configure pearOS-installer origin" 1
    git -C "${pacstrap_dir}/usr/share/pearOS-installer" fetch --depth=1 origin @COMMIT@ || _msg_error "Failed to fetch pinned pearOS-installer" 1
    git -C "${pacstrap_dir}/usr/share/pearOS-installer" checkout --detach FETCH_HEAD || _msg_error "Failed to check out pinned pearOS-installer" 1
    [[ "$(git -C "${pacstrap_dir}/usr/share/pearOS-installer" rev-parse HEAD)" == "@COMMIT@" ]] || _msg_error "pearOS-installer commit does not match the lock" 1
    [[ "$(git -C "${pacstrap_dir}/usr/share/pearOS-installer" rev-parse HEAD:system_install/setup)" == "@BLOB@" ]] || _msg_error "pearOS-installer setup blob does not match the lock" 1'''
new = new.replace('@COMMIT@', commit).replace('@BLOB@', setup_blob)
# The pinned builder writes its ISO pkglist before cleanup removes optional
# packages. Move the list after cleanup, but before squashfs/ISO creation, so
# it describes the installed package database in the finished live image.
build_order_anchor = '''    _run_once _make_customize_airootfs
    _run_once _make_pkglist
    if [[ "${buildmode}" == 'netboot' ]]; then
        _run_once _make_boot_on_iso9660
    else
        _run_once _make_bootmodes
    fi
    _run_once _cleanup_pacstrap_dir
    _run_once _prepare_airootfs_image'''
hook_definition_anchor = '_make_pkglist() {'
if source.count(build_order_anchor) != 1 or source.count(hook_definition_anchor) != 1:
    raise SystemExit('pinned upstream live identity/package-list layout changed')
hook_definition = '''_apply_xodus_visible_identity() {
    local helper="${profile}/xodus-apply-visible-identity.sh"
    [[ -f "$helper" ]] || _msg_error "Xodus visible identity hook is missing" 1
    bash "$helper" "${pacstrap_dir}" || _msg_error "Xodus visible identity hook failed" 1
}

'''
source = source.replace(old, new)
source = source.replace(hook_definition_anchor, hook_definition + hook_definition_anchor)
source = source.replace(
    build_order_anchor,
    '''    _run_once _make_customize_airootfs
    _run_once _apply_xodus_visible_identity
    if [[ "${buildmode}" == 'netboot' ]]; then
        _run_once _make_boot_on_iso9660
    else
        _run_once _make_bootmodes
    fi
    _run_once _cleanup_pacstrap_dir
    _run_once _make_pkglist
    _run_once _prepare_airootfs_image''',
)
builder.write_text(source)
PY
bash -n "$builder"
grep -Fq "fetch --depth=1 origin $installer_commit" "$builder"
! grep -Fq 'git clone --depth 1 https://github.com/pearOS-archlinux/pearOS-installer.git' "$builder"
grep -Fq '    _run_once _apply_xodus_visible_identity' "$builder"

# The visible identity helper runs after upstream package installation and
# live-user creation. It edits the packaged Plasma and installer files inside
# pacstrap_dir, where the profile overlay alone cannot reach them.
visible_identity_hook="$script_dir/identity/apply-visible-identity.sh"
wallpaper_source="$script_dir/identity/assets/xodus-wallpaper.png"
app_icon_source="$script_dir/identity/assets/xodus-app-icon.png"
[[ -f "$visible_identity_hook" && -s "$wallpaper_source" && -s "$app_icon_source" ]] || {
  echo 'Xodus visible identity hook or artwork is missing' >&2
  exit 66
}
install -Dm0644 "$visible_identity_hook" "$root/pear/xodus-apply-visible-identity.sh"
install -Dm0644 "$wallpaper_source" "$root/pear/airootfs/usr/share/wallpapers/Xodus/xodus-wallpaper.png"
install -Dm0644 "$app_icon_source" "$root/pear/airootfs/usr/share/pixmaps/xodus-app-icon.png"

# Fail closed if the pinned upstream shape drifts. This prevents a partially
# branded image from silently shipping after an upstream layout change.
grep -Fq 'iso_name="pearOS-NiceC0re"' "$profile"
grep -Fq 'iso_publisher="The Pear Project <https://pearos.xyz>"' "$profile"
grep -Fq 'iso_application="pearOS Live Session"' "$profile"
grep -Fq 'pearOS-Live-System' "$hostname_file"

sed -i \
  -e 's/iso_name="pearOS-NiceC0re"/iso_name="Xodus"/' \
  -e 's/iso_label="pearOS_NiceC0re_$(date +%Y%m)"/iso_label="XODUS_$(date +%Y%m)"/' \
  -e 's#iso_publisher="The Pear Project <https://pearos.xyz>"#iso_publisher="Xodus Project <https://github.com/chewtoo22-rgb/Xodus>"#' \
  -e 's/iso_application="pearOS Live Session"/iso_application="Xodus Live Session"/' \
  "$profile"

cat > "$hostname_file" <<'EOF'
# SPDX-License-Identifier: GPL-3.0-or-later
xodus-live
EOF

cat > "$motd_file" <<'EOF'
Xodus // NiceC0re Foundation
Development preview — pearOS-derived Arch Linux build.
EOF

# Build provenance inside the live filesystem. Keep both sides of the source
# boundary explicit: the exact Xodus overlay commit and the pinned upstream
# pearOS commit. Hardware evidence can then be tied back to the exact sources
# that produced the tested ISO instead of only to the upstream foundation.
install -d "$root/pear/airootfs/usr/lib/xodus"
cat > "$root/pear/airootfs/usr/lib/xodus/build-info" <<EOF
XODUS_NAME=Xodus
XODUS_CHANNEL=M0-First-Blood
XODUS_FOUNDATION=pearOS-NiceC0re
XODUS_SOURCE_COMMIT=${xodus_source_commit}
XODUS_UPSTREAM_COMMIT=${upstream_commit}
XODUS_INSTALLER_COMMIT=${installer_commit}
EOF

# Carry the read-only hardware evidence collector in the image itself. The
# collector resolves candidate provenance from build-info, so a physical NUC
# run does not depend on a network connection or a separate Git checkout.
hardware_evidence_source="$repo_root/qa/hardware-live-evidence.sh"
test -f "$hardware_evidence_source"
install -Dm0755 "$hardware_evidence_source" "$root/pear/airootfs/usr/lib/xodus/xodus-hardware-live-evidence"

# Carry the strict physical-NUC admission check and its provenance verifier in
# the same payload. This closes the final checkout dependency in the physical
# X1 test path: qualified media can prove UEFI/physical-machine/provenance state
# offline before any destructive installer step is considered.
nuc_preflight_source="$repo_root/qa/x1-nuc-preflight.sh"
build_info_verifier_source="$repo_root/qa/x1-build-info-contract.sh"
test -f "$nuc_preflight_source"
test -f "$build_info_verifier_source"
install -Dm0755 "$nuc_preflight_source" "$root/pear/airootfs/usr/lib/xodus/xodus-x1-nuc-preflight"
install -Dm0755 "$build_info_verifier_source" "$root/pear/airootfs/usr/lib/xodus/xodus-build-info-verify"

# Install the first-boot foundation into the live payload. It is intentionally
# present on live media but refuses to complete until booted from an installed
# non-ephemeral root, so the installer can copy one identical payload to disk.
first_boot_runner="$script_dir/first-boot/xodus-first-boot"
first_boot_unit="$script_dir/first-boot/xodus-first-boot.service"
test -f "$first_boot_runner"
test -f "$first_boot_unit"
install -Dm0755 "$first_boot_runner" "$root/pear/airootfs/usr/lib/xodus/xodus-first-boot"
install -Dm0644 "$first_boot_unit" "$root/pear/airootfs/usr/lib/systemd/system/xodus-first-boot.service"
install -d -m0755 "$root/pear/airootfs/var/lib/xodus/first-boot"
install -d "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants"
ln -sfn /usr/lib/systemd/system/xodus-first-boot.service \
  "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service"

# Install the independent AI first-boot state recorder. The service is safe to
# ship before the hardware selector promotion lands because systemd gates it on
# the selector path. Once scripts/xodus-ai-select.py is present, the exact same
# overlay installs it and records one immutable hardware recommendation after
# the installed-system first-boot foundation succeeds. No model is downloaded.
ai_runner="$script_dir/first-boot/xodus-ai-first-boot"
ai_unit="$script_dir/first-boot/xodus-ai-first-boot.service"
test -f "$ai_runner"
test -f "$ai_unit"
install -Dm0755 "$ai_runner" "$root/pear/airootfs/usr/lib/xodus/xodus-ai-first-boot"
install -Dm0644 "$ai_unit" "$root/pear/airootfs/usr/lib/systemd/system/xodus-ai-first-boot.service"
install -d -m0755 "$root/pear/airootfs/var/lib/xodus/ai"
ln -sfn /usr/lib/systemd/system/xodus-ai-first-boot.service \
  "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-ai-first-boot.service"
selector_source="$repo_root/scripts/xodus-ai-select.py"
if [[ -f "$selector_source" ]]; then
  install -Dm0755 "$selector_source" "$root/pear/airootfs/usr/lib/xodus/xodus-ai-select.py"
fi

# Install and enable the read-only local-inference runtime preflight alongside
# the hardware-selection service it requires. Keeping the script and unit in
# the same overlay prevents repository-valid code from silently disappearing
# from the produced live/installed payload.
runtime_preflight_source="$repo_root/scripts/xodus-ai-runtime-preflight.py"
runtime_preflight_unit="$script_dir/first-boot/xodus-ai-runtime-preflight.service"
test -f "$runtime_preflight_source"
test -f "$runtime_preflight_unit"
install -Dm0755 "$runtime_preflight_source" "$root/pear/airootfs/usr/lib/xodus/xodus-ai-runtime-preflight.py"
install -Dm0644 "$runtime_preflight_unit" "$root/pear/airootfs/usr/lib/systemd/system/xodus-ai-runtime-preflight.service"
ln -sfn /usr/lib/systemd/system/xodus-ai-runtime-preflight.service \
  "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-ai-runtime-preflight.service"

# The QEMU boot gate needs evidence from a real live Plasma session. The probe
# runs only on archiso media, so copying this payload to an installed system
# does not turn a later installed boot into a live-media QA pass.
desktop_probe_source="$script_dir/live-desktop/xodus-live-desktop-probe"
desktop_probe_unit="$script_dir/live-desktop/xodus-live-desktop-probe.service"
test -f "$desktop_probe_source"
test -f "$desktop_probe_unit"
install -Dm0755 "$desktop_probe_source" "$root/pear/airootfs/usr/lib/xodus/xodus-live-desktop-probe"
install -Dm0644 "$desktop_probe_unit" "$root/pear/airootfs/usr/lib/systemd/system/xodus-live-desktop-probe.service"
install -d "$root/pear/airootfs/etc/systemd/system/graphical.target.wants"
ln -sfn /usr/lib/systemd/system/xodus-live-desktop-probe.service \
  "$root/pear/airootfs/etc/systemd/system/graphical.target.wants/xodus-live-desktop-probe.service"

# build-binary copies the profile airootfs with --no-preserve=mode. Its later
# file_permissions pass must restore executable bits inside the squashfs;
# install -m0755 above only sets modes in the source tree.
grep -Eq '^[[:space:]]*file_permissions=\(' "$profile" || {
  echo 'pinned upstream profile no longer declares file_permissions' >&2
  exit 66
}
! grep -Fq '["/usr/lib/xodus/' "$profile" || {
  echo 'pinned upstream profile already has Xodus permissions' >&2
  exit 66
}
cat >> "$profile" <<'EOF'

# Xodus executable payloads (the builder discards source-tree modes).
file_permissions+=(
  ["/usr/lib/xodus/xodus-hardware-live-evidence"]="0:0:755"
  ["/usr/lib/xodus/xodus-x1-nuc-preflight"]="0:0:755"
  ["/usr/lib/xodus/xodus-build-info-verify"]="0:0:755"
  ["/usr/lib/xodus/xodus-first-boot"]="0:0:755"
  ["/usr/lib/xodus/xodus-ai-first-boot"]="0:0:755"
  ["/usr/lib/xodus/xodus-ai-runtime-preflight.py"]="0:0:755"
  ["/usr/lib/xodus/xodus-live-desktop-probe"]="0:0:755"
)
EOF
if [[ -f "$root/pear/airootfs/usr/lib/xodus/xodus-ai-select.py" ]]; then
  cat >> "$profile" <<'EOF'
file_permissions["/usr/lib/xodus/xodus-ai-select.py"]="0:0:755"
EOF
fi
bash -n "$profile"

# Assertions are part of the contract: a successful overlay must leave no
# upstream pearOS ISO identity in the profile metadata.
grep -Fq 'iso_name="Xodus"' "$profile"
grep -Fq 'iso_application="Xodus Live Session"' "$profile"
grep -Fq 'xodus-live' "$hostname_file"
! grep -Fq 'iso_name="pearOS-NiceC0re"' "$profile"
grep -Fxq "XODUS_SOURCE_COMMIT=${xodus_source_commit}" "$root/pear/airootfs/usr/lib/xodus/build-info"
grep -Fxq "XODUS_UPSTREAM_COMMIT=${upstream_commit}" "$root/pear/airootfs/usr/lib/xodus/build-info"
grep -Fxq "XODUS_INSTALLER_COMMIT=${installer_commit}" "$root/pear/airootfs/usr/lib/xodus/build-info"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-hardware-live-evidence"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-x1-nuc-preflight"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-build-info-verify"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-first-boot"
test -d "$root/pear/airootfs/var/lib/xodus/first-boot"
test -L "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-ai-first-boot"
test -d "$root/pear/airootfs/var/lib/xodus/ai"
test -L "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-ai-first-boot.service"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-ai-runtime-preflight.py"
test -f "$root/pear/airootfs/usr/lib/systemd/system/xodus-ai-runtime-preflight.service"
test -L "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-ai-runtime-preflight.service"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-live-desktop-probe"
test -f "$root/pear/airootfs/usr/lib/systemd/system/xodus-live-desktop-probe.service"
test -L "$root/pear/airootfs/etc/systemd/system/graphical.target.wants/xodus-live-desktop-probe.service"

echo "Applied Xodus M0 identity overlay to $root"

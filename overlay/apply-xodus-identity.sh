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
EOF

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

# Assertions are part of the contract: a successful overlay must leave no
# upstream pearOS ISO identity in the profile metadata.
grep -Fq 'iso_name="Xodus"' "$profile"
grep -Fq 'iso_application="Xodus Live Session"' "$profile"
grep -Fq 'xodus-live' "$hostname_file"
! grep -Fq 'iso_name="pearOS-NiceC0re"' "$profile"
grep -Fxq "XODUS_SOURCE_COMMIT=${xodus_source_commit}" "$root/pear/airootfs/usr/lib/xodus/build-info"
grep -Fxq "XODUS_UPSTREAM_COMMIT=${upstream_commit}" "$root/pear/airootfs/usr/lib/xodus/build-info"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-first-boot"
test -d "$root/pear/airootfs/var/lib/xodus/first-boot"
test -L "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-ai-first-boot"
test -d "$root/pear/airootfs/var/lib/xodus/ai"
test -L "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-ai-first-boot.service"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-ai-runtime-preflight.py"
test -f "$root/pear/airootfs/usr/lib/systemd/system/xodus-ai-runtime-preflight.service"
test -L "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-ai-runtime-preflight.service"

echo "Applied Xodus M0 identity overlay to $root"

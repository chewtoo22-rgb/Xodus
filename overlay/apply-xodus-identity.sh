#!/usr/bin/env bash
set -euo pipefail

root=${1:-}
if [[ -z "$root" || ! -d "$root/pear/airootfs" || ! -f "$root/pear/profiledef.sh" ]]; then
  echo "usage: $0 <pearOS-iso-source-root>" >&2
  exit 64
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
profile="$root/pear/profiledef.sh"
hostname_file="$root/pear/airootfs/etc/hostname"
motd_file="$root/pear/airootfs/etc/motd"

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

# Build provenance inside the live filesystem. Keep upstream attribution
# explicit while making the Xodus layer and source pin machine-readable.
install -d "$root/pear/airootfs/usr/lib/xodus"
cat > "$root/pear/airootfs/usr/lib/xodus/build-info" <<EOF
XODUS_NAME=Xodus
XODUS_CHANNEL=M0-First-Blood
XODUS_FOUNDATION=pearOS-NiceC0re
XODUS_UPSTREAM_COMMIT=${XODUS_UPSTREAM_COMMIT:-unknown}
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
# The hardened unit exposes only this state directory as writable, so it must
# already exist before systemd constructs the service mount namespace.
install -d -m0755 "$root/pear/airootfs/var/lib/xodus/first-boot"
install -d "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants"
ln -sfn /usr/lib/systemd/system/xodus-first-boot.service \
  "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service"

# Assertions are part of the contract: a successful overlay must leave no
# upstream pearOS ISO identity in the profile metadata.
grep -Fq 'iso_name="Xodus"' "$profile"
grep -Fq 'iso_application="Xodus Live Session"' "$profile"
grep -Fq 'xodus-live' "$hostname_file"
! grep -Fq 'iso_name="pearOS-NiceC0re"' "$profile"
test -x "$root/pear/airootfs/usr/lib/xodus/xodus-first-boot"
test -d "$root/pear/airootfs/var/lib/xodus/first-boot"
test -L "$root/pear/airootfs/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service"

echo "Applied Xodus M0 identity overlay to $root"

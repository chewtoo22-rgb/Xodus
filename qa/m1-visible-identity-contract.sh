#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
overlay="$repo_root/overlay/apply-xodus-identity.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

make_source_fixture() {
  local source_root=$1
  mkdir -p "$source_root/pear/airootfs/etc"
  cat > "$source_root/pear/profiledef.sh" <<'EOF'
iso_name="pearOS-NiceC0re"
iso_label="pearOS_NiceC0re_$(date +%Y%m)"
iso_publisher="The Pear Project <https://pearos.xyz>"
iso_application="pearOS Live Session"
file_permissions=()
EOF
  echo pearOS-Live-System > "$source_root/pear/airootfs/etc/hostname"
  cat > "$source_root/build-binary" <<'EOF'
#!/usr/bin/env bash
_make_custom_airootfs() {
    # Clone pearOS-installer from GitHub instead of using local files
    git clone --depth 1 https://github.com/pearOS-archlinux/pearOS-installer.git "${pacstrap_dir}/usr/share/pearOS-installer" || _msg_error "Failed to clone pearOS-installer from GitHub" 1
}
_make_pkglist() { :; }
_make_image() {
    _run_once _make_customize_airootfs
    _run_once _make_pkglist
}
EOF
}

make_source_fixture "$tmp/source"
bash "$overlay" "$tmp/source" >/dev/null
builder="$tmp/source/build-binary"
hook="$tmp/source/pear/xodus-apply-visible-identity.sh"
bash -n "$builder"
bash -n "$hook"
python3 - "$builder" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
assert source.count('_apply_xodus_visible_identity() {') == 1
assert source.count('    _run_once _make_customize_airootfs\n    _run_once _apply_xodus_visible_identity\n    _run_once _make_pkglist') == 1
assert source.count('bash "$helper" "${pacstrap_dir}" || _msg_error') == 1
PY

live="$tmp/live"
for home in etc/skel home/liveuser; do
  mkdir -p "$live/$home/.config" "$live/$home/Desktop"
  cat > "$live/$home/.config/plasma-org.kde.plasma.desktop-appletsrc" <<'EOF'
[Containments][1][Wallpaper][org.kde.image][General]
Image=file:///usr/share/extras/wallpapers/Default/dark-mode.jpg
[Containments][2][Wallpaper][org.kde.image][General]
Image=file:///usr/share/extras/wallpapers/Default/dark-mode.jpg
EOF
  cp "$live/$home/.config/plasma-org.kde.plasma.desktop-appletsrc" \
    "$live/$home/.config/plasma-org.kde.plasma.desktop-appletsrc.bak"
  cat > "$live/$home/Desktop/system_install.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Install pearOS NiceC0re
GenericName=pearOS Installer
Exec=bash bin_install
Comment=pearOS installer
Icon=nicec0re-logo
X-Upstream-Credit=pearOS
EOF
done
mkdir -p "$live/usr/share/wallpapers/Xodus" "$live/usr/share/pixmaps"
cp "$tmp/source/pear/airootfs/usr/share/wallpapers/Xodus/xodus-wallpaper.png" \
  "$live/usr/share/wallpapers/Xodus/xodus-wallpaper.png"
cp "$tmp/source/pear/airootfs/usr/share/pixmaps/xodus-app-icon.png" \
  "$live/usr/share/pixmaps/xodus-app-icon.png"
cmp "$repo_root/overlay/identity/assets/xodus-wallpaper.png" "$live/usr/share/wallpapers/Xodus/xodus-wallpaper.png"
cmp "$repo_root/overlay/identity/assets/xodus-app-icon.png" "$live/usr/share/pixmaps/xodus-app-icon.png"
cp -a "$live" "$tmp/original"

bash "$hook" "$live" >/dev/null
for home in etc/skel home/liveuser; do
  for suffix in '' .bak; do
    config="$live/$home/.config/plasma-org.kde.plasma.desktop-appletsrc$suffix"
    test "$(grep -Fc 'Image=file:///usr/share/wallpapers/Xodus/xodus-wallpaper.png' "$config")" -eq 2
    ! grep -Fq 'Image=file:///usr/share/extras/wallpapers/Default/dark-mode.jpg' "$config"
  done
  launcher="$live/$home/Desktop/system_install.desktop"
  grep -Fxq 'Name=Install Xodus' "$launcher"
  grep -Fxq 'GenericName=Xodus Installer' "$launcher"
  grep -Fxq 'Comment=Install Xodus to this computer' "$launcher"
  grep -Fxq 'Icon=/usr/share/pixmaps/xodus-app-icon.png' "$launcher"
  grep -Fxq 'Exec=bash bin_install' "$launcher"
  grep -Fxq 'X-Upstream-Credit=pearOS' "$launcher"
done

# A changed source layout aborts the overlay rather than silently skipping the
# build hook. A changed live config aborts before modifying any other file.
make_source_fixture "$tmp/source-drift"
sed -i '/_run_once _make_customize_airootfs/d' "$tmp/source-drift/build-binary"
if bash "$overlay" "$tmp/source-drift" >"$tmp/source-drift.log" 2>&1; then
  echo 'overlay accepted missing upstream build hook anchor' >&2
  exit 1
fi
grep -Fq 'pinned upstream live identity hook layout changed' "$tmp/source-drift.log"

cp -a "$tmp/original" "$tmp/bad-config"
sed -i '0,/dark-mode.jpg/s/dark-mode.jpg/new-default.jpg/' \
  "$tmp/bad-config/etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc"
cp -a "$tmp/bad-config" "$tmp/bad-config-before"
if bash "$hook" "$tmp/bad-config" >"$tmp/bad-config.log" 2>&1; then
  echo 'identity hook accepted a changed wallpaper config' >&2
  exit 1
fi
grep -Fq 'unexpected Plasma wallpaper layout' "$tmp/bad-config.log"
diff -qr "$tmp/bad-config-before" "$tmp/bad-config"

cp -a "$tmp/original" "$tmp/bad-launcher"
sed -i 's/Exec=bash bin_install/Exec=unexpected/' \
  "$tmp/bad-launcher/home/liveuser/Desktop/system_install.desktop"
cp -a "$tmp/bad-launcher" "$tmp/bad-launcher-before"
if bash "$hook" "$tmp/bad-launcher" >"$tmp/bad-launcher.log" 2>&1; then
  echo 'identity hook accepted a changed installer command' >&2
  exit 1
fi
grep -Fq 'unexpected installer desktop entry' "$tmp/bad-launcher.log"
diff -qr "$tmp/bad-launcher-before" "$tmp/bad-launcher"

echo 'M1 visible identity hook contract: PASS'

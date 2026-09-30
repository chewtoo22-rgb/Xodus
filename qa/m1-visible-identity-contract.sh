#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
overlay=${XODUS_TEST_IDENTITY_OVERLAY:-"$repo_root/overlay/apply-xodus-identity.sh"}
[[ -f "$overlay" && ! -L "$overlay" ]]
# Every derivation and captured live payload must carry the same exact source.
export XODUS_SOURCE_COMMIT=0123456789abcdef0123456789abcdef01234567
export XODUS_UPSTREAM_COMMIT=89abcdef0123456789abcdef0123456789abcdef
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
_build_iso_base() {
    _run_once _make_customize_airootfs
    _run_once _make_pkglist
    if [[ "${buildmode}" == 'netboot' ]]; then
        _run_once _make_boot_on_iso9660
    else
        _run_once _make_bootmodes
    fi
    _run_once _cleanup_pacstrap_dir
    _run_once _prepare_airootfs_image
}
EOF
  python3 "$repo_root/qa/boot_identity_fixture.py" "$source_root"
}

make_source_fixture "$tmp/source"
bash "$overlay" "$tmp/source" >/dev/null
builder="$tmp/source/build-binary"
hook="$tmp/source/pear/xodus-apply-visible-identity.sh"
welcome_builder="$tmp/source/pear/xodus-build-welcome.sh"
welcome_source="$tmp/source/pear/xodus-welcome.cpp"
bash -n "$builder"
bash -n "$hook"
bash -n "$welcome_builder"
cmp "$repo_root/overlay/identity/welcome/xodus-welcome.cpp" "$welcome_source"
python3 - "$repo_root" "$tmp/source/pear" "$builder" "$XODUS_SOURCE_COMMIT" <<'PY'
from pathlib import Path
import subprocess
import sys

repo, profile, builder = map(Path, sys.argv[1:4])
source_commit = sys.argv[4]
for component in ('shell', 'settings', 'installer', 'installed'):
    directory = repo / 'overlay/identity' / component
    staged = profile / ('xodus-' + component)
    assert staged.is_dir() and not staged.is_symlink(), 'missing staged component: ' + component
    originals = [path for path in directory.rglob('*') if path.is_file()
                 and '__pycache__' not in path.parts and path.suffix != '.pyc']
    assert originals, 'empty source component: ' + component
    for path in originals:
        target = staged / path.relative_to(directory)
        assert target.is_file() and not target.is_symlink(), 'unsafe/missing staged source: ' + str(target)
        assert target.read_bytes() == path.read_bytes(), 'changed staged source: ' + str(target)
shell = profile / 'xodus-apply-shell-identity.sh'
assert shell.read_bytes() == (repo / 'overlay/identity/apply-shell-identity.sh').read_bytes()
checker = repo / 'qa/verify-graphical-identity.py'
graphical = profile / 'xodus-graphical-contract'
assert (graphical / 'qa/verify-graphical-identity.py').read_bytes() == checker.read_bytes()
references = subprocess.check_output([sys.executable, str(checker), '--list-reference-files'], text=True).splitlines()
assert len(references) == 11 and len(set(references)) == 11
expected = {'qa/verify-graphical-identity.py', *references}
actual = {path.relative_to(graphical).as_posix() for path in graphical.rglob('*') if path.is_file()}
assert actual == expected, 'staged graphical reference inventory differs'
for relative in references:
    assert (graphical / relative).read_bytes() == (repo / relative).read_bytes(), relative
text = builder.read_text()
assert text.count('--source-commit ' + source_commit + ' --build-info') == 1, 'installer derivation source differs'
assert '@XODUS_SOURCE@' not in text
info = (profile / 'airootfs/usr/lib/xodus/build-info').read_text().splitlines()
assert info.count('XODUS_SOURCE_COMMIT=' + source_commit) == 1, 'live provenance source differs'
for helper in ('xodus-identity-payload', 'xodus-restore-user-identity'):
    assert not (profile / 'airootfs/usr/lib/xodus' / helper).exists(), 'late helper incorrectly staged before customize'
PY
grep -Fq 'pacman -S --needed --noconfirm qt5-base pkgconf' "$builder"
grep -Fq 'bash "$welcome_builder" "${profile}" "${pacstrap_dir}"' "$builder"
mkdir -p "$tmp/mock-tools" "$tmp/mock-live"
cat > "$tmp/mock-tools/pkg-config" <<'EOF'
#!/usr/bin/env bash
[[ "$*" == '--atleast-version=5.15 Qt5Widgets' ||
   "$*" == '--cflags --libs Qt5Widgets' ]]
EOF
cat > "$tmp/mock-tools/c++" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
for ((i = 1; i <= $#; i++)); do
  if [[ "${!i}" == -o ]]; then
    next=$((i + 1))
    printf '\177ELF\002\001\001\000' > "${!next}"
    exit 0
  fi
done
exit 88
EOF
chmod 0755 "$tmp/mock-tools/pkg-config" "$tmp/mock-tools/c++"
PATH="$tmp/mock-tools:$PATH" bash "$welcome_builder" "$tmp/source/pear" "$tmp/mock-live"
test -x "$tmp/mock-live/usr/lib/xodus/xodus-welcome"
test ! -e "$tmp/source/pear/airootfs/usr/lib/xodus/xodus-welcome"
python3 - "$builder" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
assert source.count('_apply_xodus_visible_identity() {') == 1
assert source.count('    _run_once _make_customize_airootfs\n    _run_once _apply_xodus_visible_identity') == 1
assert source.count('    _run_once _cleanup_pacstrap_dir\n    _run_once _make_pkglist\n    _run_once _prepare_airootfs_image') == 1
assert source.count('bash "$helper" "${pacstrap_dir}" || _msg_error') == 1
PY
python3 "$repo_root/qa/generated_identity_hook_fixture.py" "$builder" \
  "$tmp/source/pear" "$tmp/generated-hook" "$XODUS_SOURCE_COMMIT"

# Upstream cleanup removes optional packages after constructing the live root.
# The ISO pkglist must reflect that final state before image creation.
bash -s -- "$builder" "$tmp/packages" "$tmp/pkglist" <<'BASH'
set -euo pipefail
source "$1"
packages=$2
pkglist=$3
_run_once() { "$1"; }
_make_customize_airootfs() { :; }
_apply_xodus_visible_identity() { :; }
_make_bootmodes() { :; }
_cleanup_pacstrap_dir() { printf 'base\n' > "$packages"; }
_make_pkglist() { cp "$packages" "$pkglist"; }
_prepare_airootfs_image() { :; }
printf 'base\nkinfocenter\n' > "$packages"
buildmode=iso
_build_iso_base
BASH
test "$(cat "$tmp/pkglist")" = base

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
mkdir -p "$live/usr/lib/xodus" "$live/usr/bin" \
  "$live/usr/share/applications" "$live/etc/skel/.config/autostart" \
  "$live/home/liveuser/.config/autostart"
printf '\177ELF\002\001\001\000' > "$live/usr/lib/xodus/xodus-welcome"
chmod 0755 "$live/usr/lib/xodus/xodus-welcome"
printf '#!/bin/sh\nexit 0\n' > "$live/usr/bin/pearos-welcome"
cat > "$live/usr/share/applications/welcome.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Welcome
Exec=pearos-welcome
Icon=/usr/share/pixmaps/welcome.png
Comment=pearOS - Welcome App
EOF
cp "$live/usr/share/applications/welcome.desktop" \
  "$live/etc/skel/.config/autostart/welcome.desktop"
cp "$live/usr/share/applications/welcome.desktop" \
  "$live/home/liveuser/.config/autostart/welcome.desktop"
mkdir -p "$tmp/fakebin"
cat > "$tmp/fakebin/arch-chroot" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$XODUS_TEST_CHROOT_LOG"
if [[ "$2" == /usr/bin/ldd ]]; then
  if [[ "${XODUS_TEST_ABI_FAIL:-0}" == 1 ]]; then
    echo 'libQt5Widgets.so.5 => not found'
  else
    printf '%s\n' 'libQt5Widgets.so.5 => /usr/lib/libQt5Widgets.so.5' \
      'libQt5Gui.so.5 => /usr/lib/libQt5Gui.so.5' \
      'libQt5Core.so.5 => /usr/lib/libQt5Core.so.5'
  fi
elif [[ "$2" != /usr/bin/env || "${@: -2:1}" != /usr/lib/xodus/xodus-welcome ||
        "${@: -1}" != --self-test ]]; then
  exit 88
fi
EOF
chmod 0755 "$tmp/fakebin/arch-chroot"
export XODUS_TEST_CHROOT_LOG="$tmp/chroot-calls"
export PATH="$tmp/fakebin:$PATH"
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
for home in etc/skel home/liveuser; do
  autostart="$live/$home/.config/autostart"
  grep -Fxq 'Hidden=true' "$autostart/welcome.desktop"
  grep -Fxq 'Exec=/usr/lib/xodus/xodus-welcome' "$autostart/xodus-welcome.desktop"
  grep -Fxq 'OnlyShowIn=KDE;' "$autostart/xodus-welcome.desktop"
done
grep -Fxq 'Hidden=true' "$live/usr/share/applications/welcome.desktop"
grep -Fxq 'Exec=/usr/lib/xodus/xodus-welcome' \
  "$live/usr/share/applications/xodus-welcome.desktop"
! grep -Eiq 'pearOS|pearos' "$live/usr/share/applications/xodus-welcome.desktop" \
  "$live/etc/skel/.config/autostart/xodus-welcome.desktop" \
  "$live/home/liveuser/.config/autostart/xodus-welcome.desktop"
test "$(wc -l < "$XODUS_TEST_CHROOT_LOG")" -eq 2
grep -Fq '/usr/bin/ldd /usr/lib/xodus/xodus-welcome' "$XODUS_TEST_CHROOT_LOG"
grep -Fq '/usr/lib/xodus/xodus-welcome --self-test' "$XODUS_TEST_CHROOT_LOG"

# A changed source layout aborts the overlay rather than silently skipping the
# build hook. A changed live config aborts before modifying any other file.
make_source_fixture "$tmp/source-drift"
sed -i '/_run_once _make_customize_airootfs/d' "$tmp/source-drift/build-binary"
if bash "$overlay" "$tmp/source-drift" >"$tmp/source-drift.log" 2>&1; then
  echo 'overlay accepted missing upstream build hook anchor' >&2
  exit 1
fi
grep -Fq 'pinned upstream live identity/package-list layout changed' "$tmp/source-drift.log"

make_source_fixture "$tmp/order-drift"
sed -i '/_run_once _cleanup_pacstrap_dir/d' "$tmp/order-drift/build-binary"
if bash "$overlay" "$tmp/order-drift" >"$tmp/order-drift.log" 2>&1; then
  echo 'overlay accepted changed upstream package cleanup order' >&2
  exit 1
fi
grep -Fq 'pinned upstream live identity/package-list layout changed' "$tmp/order-drift.log"

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

cp -a "$tmp/original" "$tmp/bad-welcome"
sed -i 's/Exec=pearos-welcome/Exec=other-welcome/' \
  "$tmp/bad-welcome/usr/share/applications/welcome.desktop"
cp -a "$tmp/bad-welcome" "$tmp/bad-welcome-before"
if bash "$hook" "$tmp/bad-welcome" >"$tmp/bad-welcome.log" 2>&1; then
  echo 'identity hook accepted changed upstream Welcome entry' >&2
  exit 1
fi
grep -Fq 'upstream Welcome entry changed' "$tmp/bad-welcome.log"
diff -qr "$tmp/bad-welcome-before" "$tmp/bad-welcome"

cp -a "$tmp/original" "$tmp/bad-abi"
cp -a "$tmp/bad-abi" "$tmp/bad-abi-before"
if XODUS_TEST_ABI_FAIL=1 bash "$hook" "$tmp/bad-abi" >"$tmp/bad-abi.log" 2>&1; then
  echo 'identity hook accepted missing Welcome Qt libraries' >&2
  exit 1
fi
grep -Fq 'Xodus Welcome is incompatible with the live root' "$tmp/bad-abi.log"
diff -qr "$tmp/bad-abi-before" "$tmp/bad-abi"

echo 'M1 visible identity hook contract: PASS'

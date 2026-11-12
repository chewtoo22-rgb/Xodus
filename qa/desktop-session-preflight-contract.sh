#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
probe="$repo_root/qa/desktop-session-preflight.sh"
bash -n "$probe"

run_probe() {
  local root=$1
  XODUS_DESKTOP_ROOT="$root" bash "$probe"
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

make_root() {
  local r=$1
  mkdir -p \
    "$r/usr/share/wayland-sessions" \
    "$r/etc/systemd/system/graphical.target.wants" \
    "$r/usr/lib/systemd/system" \
    "$r/usr/bin"
  printf '[Unit]\nDescription=fixture display manager\n' > "$r/usr/lib/systemd/system/sddm.service"
  printf '[Unit]\nDescription=fixture display manager\n' > "$r/usr/lib/systemd/system/gdm.service"
  printf '[Unit]\nDescription=fixture display manager\n' > "$r/usr/lib/systemd/system/lightdm.service"
}

add_session() {
  local r=$1
  printf '[Desktop Entry]\nName=Xodus Test\nExec=true\nType=Application\n' > "$r/usr/share/wayland-sessions/xodus.desktop"
}

r1="$tmp/ready"
make_root "$r1"
add_session "$r1"
ln -s /usr/lib/systemd/system/sddm.service "$r1/etc/systemd/system/display-manager.service"
touch "$r1/usr/bin/pipewire" "$r1/usr/bin/xdg-open"
out=$(run_probe "$r1")
grep -qx 'desktop_ready=true' <<<"$out"
grep -qx 'blockers=' <<<"$out"
grep -qx 'hardware_validation_claim=false' <<<"$out"

r2="$tmp/no-session"
make_root "$r2"
ln -s /usr/lib/systemd/system/sddm.service "$r2/etc/systemd/system/display-manager.service"
if run_probe "$r2" >"$tmp/no-session.out" 2>&1; then exit 1; fi
grep -q 'no_desktop_session' "$tmp/no-session.out"

r3="$tmp/no-dm"
make_root "$r3"
add_session "$r3"
if run_probe "$r3" >"$tmp/no-dm.out" 2>&1; then exit 1; fi
grep -q 'display_manager_not_enabled' "$tmp/no-dm.out"

r4="$tmp/warnings"
make_root "$r4"
add_session "$r4"
ln -s /usr/lib/systemd/system/gdm.service "$r4/etc/systemd/system/display-manager.service"
out=$(run_probe "$r4")
grep -qx 'desktop_ready=true' <<<"$out"
grep -q 'pipewire_not_detected' <<<"$out"
grep -q 'xdg_open_not_detected' <<<"$out"

# A dangling display-manager alias must not count as enabled.
r5="$tmp/dangling-dm"
make_root "$r5"
add_session "$r5"
ln -s /usr/lib/systemd/system/missing.service "$r5/etc/systemd/system/display-manager.service"
if run_probe "$r5" >"$tmp/dangling-dm.out" 2>&1; then exit 1; fi
grep -q 'display_manager_not_enabled' "$tmp/dangling-dm.out"

# A relative symlink that escapes the installed root must fail closed even when
# the host target exists.
r6="$tmp/external-dm"
make_root "$r6"
add_session "$r6"
printf '[Unit]\nDescription=outside fixture\n' > "$tmp/outside.service"
ln -s "../../../../../outside.service" "$r6/etc/systemd/system/display-manager.service"
if run_probe "$r6" >"$tmp/external-dm.out" 2>&1; then exit 1; fi
grep -q 'display_manager_not_enabled' "$tmp/external-dm.out"

# graphically-enabled concrete wants entries must also resolve to a real unit.
r7="$tmp/wants-valid"
make_root "$r7"
add_session "$r7"
ln -s /usr/lib/systemd/system/lightdm.service "$r7/etc/systemd/system/graphical.target.wants/lightdm.service"
out=$(run_probe "$r7")
grep -qx 'desktop_ready=true' <<<"$out"

r8="$tmp/wants-dangling"
make_root "$r8"
add_session "$r8"
ln -s /usr/lib/systemd/system/missing.service "$r8/etc/systemd/system/graphical.target.wants/sddm.service"
if run_probe "$r8" >"$tmp/wants-dangling.out" 2>&1; then exit 1; fi
grep -q 'display_manager_not_enabled' "$tmp/wants-dangling.out"

# Session directories themselves cannot be symlink substitutions.
r9="$tmp/session-dir-symlink"
make_root "$r9"
rm -rf "$r9/usr/share/wayland-sessions"
mkdir -p "$tmp/outside-sessions"
printf '[Desktop Entry]\nName=Outside\nExec=true\nType=Application\n' > "$tmp/outside-sessions/xodus.desktop"
ln -s "$tmp/outside-sessions" "$r9/usr/share/wayland-sessions"
ln -s /usr/lib/systemd/system/sddm.service "$r9/etc/systemd/system/display-manager.service"
if run_probe "$r9" >"$tmp/session-dir-symlink.out" 2>&1; then exit 1; fi
grep -q 'no_desktop_session' "$tmp/session-dir-symlink.out"

echo 'desktop session preflight contract: PASS'

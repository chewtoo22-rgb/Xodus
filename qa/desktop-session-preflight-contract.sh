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
  mkdir -p "$r/usr/share/wayland-sessions" "$r/etc/systemd/system" "$r/usr/bin"
}

r1="$tmp/ready"
make_root "$r1"
printf '[Desktop Entry]\nName=Xodus Test\nExec=true\nType=Application\n' > "$r1/usr/share/wayland-sessions/xodus.desktop"
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
printf '[Desktop Entry]\nName=Xodus Test\nExec=true\nType=Application\n' > "$r3/usr/share/wayland-sessions/xodus.desktop"
if run_probe "$r3" >"$tmp/no-dm.out" 2>&1; then exit 1; fi
grep -q 'display_manager_not_enabled' "$tmp/no-dm.out"

r4="$tmp/warnings"
make_root "$r4"
printf '[Desktop Entry]\nName=Xodus Test\nExec=true\nType=Application\n' > "$r4/usr/share/wayland-sessions/xodus.desktop"
ln -s /usr/lib/systemd/system/gdm.service "$r4/etc/systemd/system/display-manager.service"
out=$(run_probe "$r4")
grep -qx 'desktop_ready=true' <<<"$out"
grep -q 'pipewire_not_detected' <<<"$out"
grep -q 'xdg_open_not_detected' <<<"$out"

echo 'desktop session preflight contract: PASS'

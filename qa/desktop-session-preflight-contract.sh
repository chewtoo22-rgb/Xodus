#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
probe="$repo_root/qa/desktop-session-preflight.sh"
bash -n "$probe"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

make_root() {
  local r=$1
  mkdir -p "$r/usr/share/wayland-sessions" "$r/etc/systemd/system" "$r/usr/bin"
}

# Ready image: session + enabled display-manager alias.
r1="$tmp/ready"
make_root "$r1"
printf '[Desktop Entry]\nName=Xodus Test\nExec=true\nType=Application\n' > "$r1/usr/share/wayland-sessions/xodus.desktop"
ln -s /usr/lib/systemd/system/sddm.service "$r1/etc/systemd/system/display-manager.service"
touch "$r1/usr/bin/pipewire" "$r1/usr/bin/xdg-open"
out=$(XODUS_DESKTOP_ROOT="$r1" "$probe")
grep -qx 'desktop_ready=true' <<<"$out"
grep -qx 'blockers=' <<<"$out"
grep -qx 'hardware_validation_claim=false' <<<"$out"

# No session must fail closed.
r2="$tmp/no-session"
make_root "$r2"
ln -s /usr/lib/systemd/system/sddm.service "$r2/etc/systemd/system/display-manager.service"
if XODUS_DESKTOP_ROOT="$r2" "$probe" >"$tmp/no-session.out" 2>&1; then
  echo 'expected no-session fixture to fail' >&2
  exit 1
fi
grep -q 'no_desktop_session' "$tmp/no-session.out"

# Session without enabled DM must fail closed.
r3="$tmp/no-dm"
make_root "$r3"
printf '[Desktop Entry]\nName=Xodus Test\nExec=true\nType=Application\n' > "$r3/usr/share/wayland-sessions/xodus.desktop"
if XODUS_DESKTOP_ROOT="$r3" "$probe" >"$tmp/no-dm.out" 2>&1; then
  echo 'expected no-DM fixture to fail' >&2
  exit 1
fi
grep -q 'display_manager_not_enabled' "$tmp/no-dm.out"

# Missing optional desktop plumbing must warn, not block.
r4="$tmp/warnings"
make_root "$r4"
printf '[Desktop Entry]\nName=Xodus Test\nExec=true\nType=Application\n' > "$r4/usr/share/wayland-sessions/xodus.desktop"
ln -s /usr/lib/systemd/system/gdm.service "$r4/etc/systemd/system/display-manager.service"
out=$(XODUS_DESKTOP_ROOT="$r4" "$probe")
grep -qx 'desktop_ready=true' <<<"$out"
grep -q 'pipewire_not_detected' <<<"$out"
grep -q 'xdg_open_not_detected' <<<"$out"

echo 'desktop session preflight contract: PASS'

#!/usr/bin/env bash
set -euo pipefail

root=${XODUS_DESKTOP_ROOT:-/}
[[ -d "$root" ]] || { echo "desktop-preflight: root does not exist: $root" >&2; exit 64; }
root=$(cd "$root" && pwd -P)

blockers=()
warnings=()

has_session=0
for dir in "$root/usr/share/wayland-sessions" "$root/usr/share/xsessions"; do
  if [[ -d "$dir" ]] && find "$dir" -maxdepth 1 -type f -name '*.desktop' -print -quit | grep -q .; then
    has_session=1
    break
  fi
done
(( has_session == 1 )) || blockers+=("no_desktop_session")

# Installed images should expose the display-manager alias. Accept either the
# systemd alias or a concrete enabled DM unit; this probe never enables one.
has_dm=0
if [[ -L "$root/etc/systemd/system/display-manager.service" ]]; then
  has_dm=1
else
  for unit in sddm.service gdm.service lightdm.service; do
    if [[ -e "$root/etc/systemd/system/graphical.target.wants/$unit" ]]; then
      has_dm=1
      break
    fi
  done
fi
(( has_dm == 1 )) || blockers+=("display_manager_not_enabled")

[[ -e "$root/usr/bin/pipewire" || -e "$root/usr/bin/pipewire-pulse" ]] || warnings+=("pipewire_not_detected")
[[ -e "$root/usr/bin/xdg-open" ]] || warnings+=("xdg_open_not_detected")

printf 'schema=1\n'
printf 'hardware_validation_claim=false\n'
printf 'desktop_ready=%s\n' "$([[ ${#blockers[@]} -eq 0 ]] && echo true || echo false)"
printf 'blockers=%s\n' "$(IFS=,; echo "${blockers[*]-}")"
printf 'warnings=%s\n' "$(IFS=,; echo "${warnings[*]-}")"

[[ ${#blockers[@]} -eq 0 ]]

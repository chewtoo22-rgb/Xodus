#!/usr/bin/env bash
set -euo pipefail

root=${XODUS_DESKTOP_ROOT:-/}
[[ -d "$root" ]] || { echo "desktop-preflight: root does not exist: $root" >&2; exit 64; }
root=$(cd "$root" && pwd -P)

blockers=()
warnings=()

is_path_inside_root() {
  local path=$1
  [[ "$path" == "$root" || "$path" == "$root/"* ]]
}

resolve_rooted_unit() {
  local link=$1 target candidate resolved
  [[ -L "$link" ]] || return 1
  target=$(readlink -- "$link") || return 1
  [[ -n "$target" ]] || return 1

  if [[ "$target" == /* ]]; then
    candidate="$root$target"
  else
    candidate="$(dirname -- "$link")/$target"
  fi

  resolved=$(realpath -e -- "$candidate" 2>/dev/null) || return 1
  is_path_inside_root "$resolved" || return 1
  [[ -f "$resolved" && ! -L "$resolved" ]] || return 1
  printf '%s\n' "$resolved"
}

valid_session_dir() {
  local dir=$1 resolved
  [[ -d "$dir" && ! -L "$dir" ]] || return 1
  resolved=$(realpath -e -- "$dir" 2>/dev/null) || return 1
  is_path_inside_root "$resolved"
}

has_session=0
for dir in "$root/usr/share/wayland-sessions" "$root/usr/share/xsessions"; do
  if valid_session_dir "$dir" && find "$dir" -maxdepth 1 -type f -name '*.desktop' -print -quit | grep -q .; then
    has_session=1
    break
  fi
done
(( has_session == 1 )) || blockers+=("no_desktop_session")

# Installed images should expose a display-manager enablement that resolves to
# a real unit inside the installed root. Absolute systemd symlinks are resolved
# with chroot semantics (root + absolute target); external/dangling targets do
# not qualify. This probe never enables or starts a service.
has_dm=0
alias="$root/etc/systemd/system/display-manager.service"
if [[ -L "$alias" ]] && resolve_rooted_unit "$alias" >/dev/null; then
  has_dm=1
else
  wants="$root/etc/systemd/system/graphical.target.wants"
  if [[ -d "$wants" && ! -L "$wants" ]]; then
    for unit in sddm.service gdm.service lightdm.service; do
      entry="$wants/$unit"
      if [[ -L "$entry" ]] && resolve_rooted_unit "$entry" >/dev/null; then
        has_dm=1
        break
      elif [[ -f "$entry" && ! -L "$entry" ]]; then
        resolved=$(realpath -e -- "$entry" 2>/dev/null || true)
        if [[ -n "$resolved" ]] && is_path_inside_root "$resolved"; then
          has_dm=1
          break
        fi
      fi
    done
  fi
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

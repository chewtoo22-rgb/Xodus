#!/usr/bin/env bash
set -euo pipefail

root=${1:-}
outdir=${2:-}
[[ -n "$root" && -n "$outdir" ]] || {
  echo "Usage: qa/installed-system-contract.sh <installed-root> <output-dir>" >&2
  exit 64
}
[[ -d "$root" ]] || { echo "ERROR: installed root not found: $root" >&2; exit 66; }
mkdir -p "$outdir"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ -f "$root/etc/os-release" ]] || fail "missing /etc/os-release"
[[ -f "$root/etc/fstab" ]] || fail "missing /etc/fstab"
[[ -x "$root/usr/lib/systemd/systemd" || -x "$root/sbin/init" ]] || fail "missing usable init"

kernel_count=$(find "$root/boot" -maxdepth 1 -type f \( -name 'vmlinuz-*' -o -name 'linux-*' \) 2>/dev/null | wc -l | tr -d ' ')
(( kernel_count > 0 )) || fail "no installed kernel image found under /boot"

# Xodus currently installs SDDM as its graphical display-manager contract.
sddm_unit=''
for candidate in "$root/usr/lib/systemd/system/sddm.service" "$root/lib/systemd/system/sddm.service"; do
  if [[ -f "$candidate" ]]; then
    sddm_unit=$candidate
    break
  fi
done
[[ -n "$sddm_unit" ]] || fail "sddm.service is not installed"

dm_link="$root/etc/systemd/system/display-manager.service"
[[ -L "$dm_link" ]] || fail "display-manager.service is not enabled"
dm_target=$(readlink "$dm_link")
[[ "$dm_target" == *sddm.service ]] || fail "display-manager.service does not resolve to SDDM: $dm_target"

# NetworkManager must be installed and enabled for first-boot connectivity.
nm_unit=''
for candidate in "$root/usr/lib/systemd/system/NetworkManager.service" "$root/lib/systemd/system/NetworkManager.service"; do
  if [[ -f "$candidate" ]]; then
    nm_unit=$candidate
    break
  fi
done
[[ -n "$nm_unit" ]] || fail "NetworkManager.service is not installed"
nm_enabled=no
for wants in "$root/etc/systemd/system/multi-user.target.wants/NetworkManager.service" "$root/etc/systemd/system/network-online.target.wants/NetworkManager-wait-online.service"; do
  [[ -e "$wants" || -L "$wants" ]] && nm_enabled=yes
 done
[[ "$nm_enabled" == yes ]] || fail "NetworkManager is not enabled"

# Audio readiness is an installed-payload contract here. Runtime device proof is
# intentionally left to Thursday hardware evidence, because CI has no NUC audio hardware.
pipewire_bin=''
for candidate in "$root/usr/bin/pipewire" "$root/bin/pipewire"; do
  [[ -x "$candidate" ]] && { pipewire_bin=$candidate; break; }
done
[[ -n "$pipewire_bin" ]] || fail "pipewire binary is not installed"
wireplumber_bin=''
for candidate in "$root/usr/bin/wireplumber" "$root/bin/wireplumber"; do
  [[ -x "$candidate" ]] && { wireplumber_bin=$candidate; break; }
done
[[ -n "$wireplumber_bin" ]] || fail "wireplumber binary is not installed"

{
  echo "installed_system_contract=pass"
  echo "display_manager=sddm"
  echo "display_manager_alias=$dm_target"
  echo "network_manager=installed_enabled"
  echo "audio_stack=pipewire+wireplumber"
  echo "kernel_images=$kernel_count"
  echo "hardware_runtime_claim=not_automatic"
} | tee "$outdir/installed-system-contract.txt"

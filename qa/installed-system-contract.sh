#!/usr/bin/env bash
set -euo pipefail

root=${1:-}
outdir=${2:-}
boot_root=${3:-}
[[ -n "$root" && -n "$outdir" ]] || {
  echo "Usage: qa/installed-system-contract.sh <installed-root> <output-dir> [boot-root]" >&2
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

# UEFI pearOS/Xodus installs place the ESP directly at /boot. Keep the
# two-argument contract compatible with synthetic roots, but allow callers
# inspecting a real partitioned disk to supply the actual /boot filesystem.
if [[ -z "$boot_root" ]]; then
  boot_root="$root/boot"
fi
[[ -d "$boot_root" ]] || fail "installed boot root not found: $boot_root"
kernel_count=$(find "$boot_root" -maxdepth 1 -type f \( -name 'vmlinuz-*' -o -name 'linux-*' \) 2>/dev/null | wc -l | tr -d ' ')
(( kernel_count > 0 )) || fail "no installed kernel image found under installed /boot"

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

# The installed payload must retain the Xodus first-boot foundation. The live
# ISO carries the same service, but only an installed non-ephemeral root may
# complete it. Catch installer-copy regressions before a NUC boot discovers
# that first-boot state was silently omitted.
first_boot_runner="$root/usr/lib/xodus/xodus-first-boot"
first_boot_unit="$root/usr/lib/systemd/system/xodus-first-boot.service"
first_boot_link="$root/etc/systemd/system/multi-user.target.wants/xodus-first-boot.service"
first_boot_state="$root/var/lib/xodus/first-boot"
[[ -x "$first_boot_runner" ]] || fail "xodus-first-boot runner is not installed"
[[ -f "$first_boot_unit" ]] || fail "xodus-first-boot.service is not installed"
[[ -L "$first_boot_link" ]] || fail "xodus-first-boot.service is not enabled"
first_boot_target=$(readlink "$first_boot_link")
[[ "$first_boot_target" == /usr/lib/systemd/system/xodus-first-boot.service ]] || \
  fail "xodus-first-boot.service enablement target is unexpected: $first_boot_target"
[[ -d "$first_boot_state" ]] || fail "xodus first-boot state directory is missing"
[[ ! -e "$first_boot_state/complete" ]] || fail "installed image is incorrectly pre-marked first-boot complete"

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
  echo "first_boot_service=installed_enabled_pending"
  echo "audio_stack=pipewire+wireplumber"
  echo "kernel_images=$kernel_count"
  echo "boot_root=${boot_root#$root}"
  echo "hardware_runtime_claim=not_automatic"
} | tee "$outdir/installed-system-contract.txt"

#!/usr/bin/env bash
set -euo pipefail

root=${1:-}
esp=${2:-}
outdir=${3:-}
[[ -n "$root" && -n "$esp" && -n "$outdir" ]] || {
  echo "Usage: qa/installed-boot-contract.sh <installed-root> <esp-root> <output-dir>" >&2
  exit 64
}
[[ -d "$root" ]] || { echo "ERROR: installed root not found: $root" >&2; exit 66; }
[[ -d "$esp" ]] || { echo "ERROR: ESP root not found: $esp" >&2; exit 66; }
mkdir -p "$outdir"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ -f "$root/etc/os-release" ]] || fail "missing installed /etc/os-release"
[[ -f "$root/etc/fstab" ]] || fail "missing installed /etc/fstab"

# pearOS/Xodus UEFI installs place the ESP directly at /boot. Synthetic roots
# used by the standalone contract historically keep boot files under root/boot,
# so select the actual boot filesystem from fstab and retain that fallback.
boot_root="$root/boot"
if awk '!/^[[:space:]]*#/ && NF >= 2 && $2 == "/boot" { found=1 } END { exit(found ? 0 : 1) }' "$root/etc/fstab"; then
  boot_root="$esp"
fi
[[ -d "$boot_root" ]] || fail "installed boot root not found"

grub_cfg=''
for candidate in \
  "$boot_root/grub/grub.cfg" \
  "$boot_root/grub2/grub.cfg"; do
  if [[ -f "$candidate" ]]; then
    grub_cfg=$candidate
    break
  fi
done
[[ -n "$grub_cfg" ]] || fail "installed GRUB configuration not found"

kernel_count=$(find "$boot_root" -maxdepth 1 -type f -name 'vmlinuz-*' 2>/dev/null | wc -l | tr -d ' ')
initramfs_count=$(find "$boot_root" -maxdepth 1 -type f \( -name 'initramfs-*.img' -o -name 'initrd-*' \) 2>/dev/null | wc -l | tr -d ' ')
(( kernel_count > 0 )) || fail "no installed kernel image found under installed /boot"
(( initramfs_count > 0 )) || fail "no installed initramfs found under installed /boot"

# A real installed GRUB config must contain both kernel and initramfs loading.
grep -Eq '^[[:space:]]*(linux|linuxefi)[[:space:]]+' "$grub_cfg" \
  || fail "GRUB config has no kernel load command"
grep -Eq '^[[:space:]]*(initrd|initrdefi)[[:space:]]+' "$grub_cfg" \
  || fail "GRUB config has no initramfs load command"

# Reject parameters that belong to the live ArchISO boot path. Their presence in
# the installed boot config can make CI appear healthy while retaining a hidden
# dependency on installer/live media.
if grep -Eiq '(^|[[:space:]])(archisobasedir|archisolabel|img_dev|img_loop|copytoram|cow_spacesize|cow_label|cow_device)=' "$grub_cfg"; then
  grep -Ein 'archisobasedir|archisolabel|img_dev|img_loop|copytoram|cow_spacesize|cow_label|cow_device' "$grub_cfg" \
    | tee "$outdir/live-media-references.txt" >&2
  fail "installed GRUB config retains ArchISO/live-media parameters"
fi

mapfile -t efi_bins < <(find "$esp" -type f -iname '*.efi' -print 2>/dev/null)
(( ${#efi_bins[@]} > 0 )) || fail "ESP contains no EFI executable"
printf '%s\n' "${efi_bins[@]}" | sed "s#^$esp##" | sort | tee "$outdir/efi-executables.txt"

{
  echo "installed_boot_contract=pass"
  if [[ "$boot_root" == "$esp" ]]; then
    echo "boot_filesystem=esp-at-/boot"
    echo "grub_config=${grub_cfg#$esp}"
  else
    echo "boot_filesystem=root-/boot"
    echo "grub_config=${grub_cfg#$root}"
  fi
  echo "kernel_images=$kernel_count"
  echo "initramfs_images=$initramfs_count"
  echo "efi_executables=${#efi_bins[@]}"
  echo "live_media_references=none"
  echo "installer_media_claim=not_attached_by_contract"
  echo "physical_hardware_claim=not_automatic"
} | tee "$outdir/installed-boot-contract.txt"

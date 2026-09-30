#!/usr/bin/env bash
set -euo pipefail

# Run in the privileged Arch build container. Inspect the produced ISO, its
# actual FAT firmware image, squashfs and initramfs, rather than only the
# source profile or retained pacstrap directory.
root=$(realpath "${1:?usage: verify-built-boot.sh <build-root> <efi-image>}")
efi_image=$(realpath "${2:?EFI image is required}")
[[ "$root" != / && -d "$root/pear/xodus-boot-contract" &&
   "$efi_image" == "$root"/work/tmp.*/efiboot.img && -f "$efi_image" ]]
shopt -s nullglob
images=("$root"/Xodus-reference-*.iso)
(( ${#images[@]} == 1 ))
verifier="$root/pear/xodus-boot-contract/verify-boot-identity.py"
tmp=$(mktemp -d "$root/xodus-boot-audit.XXXXXX")
cleanup() {
  if mountpoint -q "$tmp/iso"; then
    umount "$tmp/iso" || return
  fi
  rm -rf -- "$tmp"
}
trap cleanup EXIT
mkdir -p "$tmp/iso" "$tmp/efi" "$tmp/initramfs"
mount -t iso9660 -o loop,ro "${images[0]}" "$tmp/iso"
mcopy -s -i "$efi_image" ::/EFI "$tmp/efi/"
python3 "$verifier" --iso-root "$tmp/iso" --efi-root "$tmp/efi"

initramfs="$tmp/iso/arch/boot/x86_64/initramfs-linux.img"
test -s "$initramfs"
(cd "$tmp/initramfs" && lsinitcpio -x "$initramfs")
python3 "$verifier" --initramfs-root "$tmp/initramfs"

squashfs="$tmp/iso/arch/x86_64/airootfs.sfs"
test -s "$squashfs"
unsquashfs -no-progress -d "$tmp/live" "$squashfs" \
  usr/share/plymouth/themes/xodus etc/plymouth/plymouthd.conf \
  etc/default/grub usr/share/grub/themes/Xodus etc/arch-release
python3 "$verifier" --live-root "$tmp/live"
echo 'Produced ISO boot identity: PASS'

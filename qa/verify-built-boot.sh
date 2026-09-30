#!/usr/bin/env bash
set -euo pipefail

# Run in the privileged Arch build container. Inspect the produced ISO, its
# actual FAT firmware image, squashfs and initramfs, rather than only the
# source profile or retained pacstrap directory.
root=$(realpath "${1:?usage: verify-built-boot.sh <build-root> <efi-image>}")
efi_image=$(realpath "${2:?EFI image is required}")
[[ "$root" != / && -d "$root" ]]
# A failed retry must not leave a previous successful graphical report behind.
rm -f -- "$root/xodus-graphical-payload-verification.json"
[[ "$root" != / && -d "$root/pear/xodus-boot-contract" &&
   -d "$root/pear/xodus-graphical-contract" &&
   "$efi_image" == "$root"/work/tmp.*/efiboot.img && -f "$efi_image" ]]
shopt -s nullglob
images=("$root"/Xodus-reference-*.iso)
(( ${#images[@]} == 1 ))
verifier="$root/pear/xodus-boot-contract/verify-boot-identity.py"
graphical_reference="$root/pear/xodus-graphical-contract"
graphical_verifier="$graphical_reference/qa/verify-graphical-identity.py"
[[ -f "$graphical_verifier" && ! -L "$graphical_verifier" ]]
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
# Obtain paths from the exact checker staged from the Xodus checkout. A file
# captures command failure before mapfile reads the resulting extraction list.
python3 "$graphical_verifier" --list-extract-paths > "$tmp/graphical-extract-paths.txt"
mapfile -t graphical_paths < "$tmp/graphical-extract-paths.txt"
(( ${#graphical_paths[@]} > 0 ))
unsquashfs -no-progress -d "$tmp/live" "$squashfs" \
  usr/share/plymouth/themes/xodus etc/plymouth/plymouthd.conf \
  etc/default/grub usr/share/grub/themes/Xodus etc/arch-release \
  "${graphical_paths[@]}"
python3 "$verifier" --live-root "$tmp/live"
python3 "$graphical_verifier" "$tmp/live" --repo-root "$graphical_reference" \
  --output "$tmp/xodus-graphical-payload-verification.json"
# Publish only after both boot and graphical payloads passed.
cp -- "$tmp/xodus-graphical-payload-verification.json" \
  "$root/xodus-graphical-payload-verification.json"
echo 'Produced ISO boot identity: PASS'
echo 'Produced ISO graphical identity: PASS'

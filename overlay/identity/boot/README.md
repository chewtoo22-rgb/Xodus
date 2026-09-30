# Xodus boot sequence

The user selected `source/xodus-boot-master.mp4` as the new Xodus boot sequence. Its SHA-256 is `1d114cddaba483c554d375a978b6474e57d20d70f88836903494c111c8ceb90b`. This video supersedes the older recovered X1 boot artwork. The original file is retained as supplied, including its audio track.

Plymouth uses 241 RGB PNG frames at the video's 24 fps cadence, exported at 960 × 540. The deployment animation is silent. PNGs preserve the film's gradients; only the 640 × 480 BIOS splash uses a 256-colour palette. Firmware and installed GRUB backgrounds derive from the same film, with a dark text area on the left.

The script loads and scales one frame at a time, centers it, and preserves its aspect ratio. It holds the final frame until the display manager takes over. It never postpones boot to finish the movie. A slow renderer can stretch animation time, and a fast boot can hand over before the final frame. Password/question prompts hide the film and use fitted white text on a dark background; password entry is masked. Escape and the retained debug/legacy boot entries remain available.

`apply-boot-identity.py` validates the approved master, every PNG dimension/checksum, and all expected pinned source anchors before making boot changes. It replaces Ploader, BIOS and Ventoy/systemd-boot menu titles, firmware artwork, the installed GRUB theme/distributor/default splash command line, and the live `/etc/arch-release` label. It selects `xodus` with `plymouth-set-default-theme -R` during upstream customization, before boot images are copied. Theme selection or initramfs rebuild errors stop the build. Upstream legal attribution remains in the repository and retained font files.

The full overlay runs `verify-boot-identity.py` against the transformed source and the staged live root after customization. The same verifier supports retained build inspection:

```sh
python3 overlay/identity/boot/verify-boot-identity.py --source-root pearos-iso
python3 overlay/identity/boot/verify-boot-identity.py --live-root extracted-squashfs
python3 overlay/identity/boot/verify-boot-identity.py --iso-root extracted-iso --efi-root extracted-efi-fat
python3 overlay/identity/boot/verify-boot-identity.py --initramfs-root unpacked-live-initramfs
python3 -m unittest discover -s qa -p test_boot_identity.py
cc -O2 -Wall -Wextra qa/plymouth-script-contract.c -ldl -lm -o /tmp/xodus-boot-check
/tmp/xodus-boot-check /usr/lib/plymouth/script.so overlay/identity/boot
```

The verifier requires the final film frame, exact reviewed theme bytes, approved export checksums, and selected `Theme=xodus`. Live-root inspection additionally checks installed GRUB configuration. Unpacking the actual live initramfs is required to prove the selected theme was included there; root filesystem checks alone do not establish that. UEFI/BIOS, Plymouth and installed GRUB screenshots on the newly built ISO remain the visual acceptance evidence.

The optional native contract uses the installed Plymouth script plugin's parser, event dispatch, math/string functions, PNG decoder and text renderer. Window and Sprite methods record layout in memory, so the check requires no DRM device and does not select a host theme. It checks proportional centering at 640 × 480, resizing to 1024 × 768, all movie frames, final-frame hold and password/question/message callbacks. It passed with Ubuntu Plymouth `24.004.60+git20250831.4a3c171d-0ubuntu8`; the Ubuntu plugin is at `/usr/lib/x86_64-linux-gnu/plymouth/script.so`. This establishes interpreter compatibility and layout behavior, while actual boot screenshots still verify the display handoff.

To regenerate the exports, install Pillow and ffmpeg and run `python3 overlay/identity/boot/source/derive-assets.py /path/to/ffmpeg`. The ISO build consumes checked-in PNGs and needs neither dependency. Regeneration changes `source/assets.sha256`; review the movie and menu contrast before accepting changed hashes. Current PNG payload size is 46,170,010 bytes.

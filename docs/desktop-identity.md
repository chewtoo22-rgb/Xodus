# Xodus M0 desktop identity

M0 deliberately keeps pearOS/NiceC0re desktop behavior intact while replacing the image-level identity in a reproducible overlay. The goal is to prove that Xodus can own its distribution identity without forking the full upstream tree.

## M0 identity contract

The build must apply `overlay/apply-xodus-identity.sh` to the exact source revision pinned in `upstream/iso.lock` before entering the Arch build container.

The overlay currently owns:

- ISO name: `Xodus`
- ISO label prefix: `XODUS_`
- publisher/application metadata
- output image filename prefix: `Xodus-reference`
- live hostname: `xodus-live`
- live MOTD
- `/usr/lib/xodus/build-info` provenance with the pinned pearOS commit

The script asserts the expected upstream strings before editing. If pearOS changes those files, the build stops rather than silently generating a half-rebranded image.

## Attribution and upstream separation

Xodus remains pearOS-derived and must retain upstream licensing and attribution. M0 does not delete pearOS license notices, package provenance, repositories, or application credits. The live MOTD and build provenance explicitly identify the NiceC0re foundation.

## Deferred visual replacements

The following remain pearOS/NiceC0re assets during M0 and will be replaced incrementally after the branded build is proven bootable:

- Plymouth/boot animation
- GRUB/Ploader artwork
- desktop wallpaper
- dock/application icons
- lock screen imagery
- sounds
- System Preferences/application branding
- Dynamic Island/notch visuals

Those replacements must not be allowed to block Thursday hardware validation. Functional boot/install evidence has priority over cosmetic completeness.

## Exit gate

A successful Desktop Identity M0 candidate must:

1. build from the same pinned upstream revision used by Core ISO;
2. produce an artifact named `Xodus-reference-*.iso`;
3. embed the Xodus ISO metadata, hostname, MOTD, and provenance file;
4. retain upstream attribution;
5. pass the existing QEMU UEFI boot-smoke workflow before hardware testing.

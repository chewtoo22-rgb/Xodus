# Xodus M0 desktop identity

M0 deliberately keeps pearOS/NiceC0re desktop behavior intact while replacing the image-level identity through a reviewable overlay. The goal is to prove that Xodus can own its distribution identity without forking the full upstream tree.

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

Those replacements do not block the M0 live-image gate. Positive desktop boot evidence takes priority over cosmetic completeness; installation has a separate safety gate.

## Exit gate

A successful Desktop Identity M0 candidate must:

1. build from the same pinned upstream revision used by Core ISO;
2. produce an artifact named `Xodus-reference-*.iso`;
3. embed the Xodus ISO metadata, hostname, MOTD, and provenance file;
4. retain upstream attribution;
5. pass the updated QEMU/OVMF gate on the same current `main` commit with retained positive graphical-session evidence. The historical watchdog-only result does not satisfy this item.

## M1 Welcome replacement

The M1 overlay builds an original Qt5 Widgets Xodus Welcome window in the Arch ISO builder. The live-root hook checks the binary against the actual live-root Qt libraries and renders it offscreen before changing desktop entries. The finished image must carry `/usr/lib/xodus/xodus-welcome` as an executable in the squashfs.

The overlay masks the upstream Welcome menu and autostart entries, adds the Xodus menu entry, and installs Xodus autostart entries for both the live user and `/etc/skel` for installed users. The window uses the Xodus charcoal, purple, and white identity. It offers an installer button only in an archiso live session, and pressing the button merely opens the existing installer. Installed sessions show Files and Settings without an installer action. Upstream package and source attribution remain in package records and project documentation rather than in the Welcome UI.

`qa/m1-visible-identity-contract.sh` checks the expected upstream launcher shape, both autostart paths, fail-closed behavior on drift, the staged Welcome executable mode, and rejection of missing Qt libraries. The post-build payload inventory also rejects a missing, non-executable, or incompletely rebranded Welcome in the retained live root. A current-head ISO build and graphical boot still need to prove the actual compiled window appears on screen.

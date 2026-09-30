# Xodus desktop identity

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

## M1 graphical payload

M1 carries the user-selected boot master under `overlay/identity/boot/source/`.
Its 241 silent Plymouth frames, GRUB/Ploader/Syslinux artwork and Xodus boot
labels are checked in the source profile and the actual produced ISO, FAT EFI
image, initramfs and squashfs. Startup is never delayed to finish the film.

The desktop payload adds original Xodus SDDM login and session splash screens,
wallpaper, color scheme and menu identity. Settings is built from its pinned
native Qt6 source and keeps functional device controls. About reads the guest
release metadata; the reviewed filesystem version and original release bytes
are retained separately. Existing package IDs remain compatible with launchers
and dock pins.

The locked installer frontend and post-install setup use the same dark purple
identity. Calamares receives a separate Xodus branding directory and selector.
Source checks preserve backend scripts, legal bodies and erase confirmation;
disk Continue remains disabled until a real disk is selected.

The online installer creates a new root from packages. The installed identity
helpers therefore verify the qualified live manifest before destructive work,
transfer boot artwork before initramfs rebuild, and transfer the full graphical
payload after package cleanup. The existing one-time first-login theme setup
restores the reviewed Xodus defaults once. Account policy, hostname and later
user preferences are preserved. Derived installer scripts are reconstructed
from the original pinned Git blobs during ISO inspection; their receipt alone
cannot authorize changed installer code.

## M1 evidence and remaining gates

The produced squashfs and retained build root must pass the same graphical
checker and have identical inspected file hashes, including the native apps.
Core retains `xodus-graphical-payload-verification.json` and
`xodus-retained-graphical-payload-verification.json`; the payload inventory binds
the report to the ISO digest and source commits. The installer live-root gate
also verifies the derived scripts, helper bytes, executable modes and closed
transfer inventory without invoking an installer.

Local and offscreen renders validate implementation surfaces. M1 completion
requires a fresh final-head Core ISO, strict QEMU desktop readiness and reviewed
boot/desktop frames, plus installer rehearsal, destructive disposable VM install
and detached installed-system boot evidence. Login authentication, lock-screen
operation and installed first-login appearance need real runtime review. This
document does not claim those remaining gates have passed.

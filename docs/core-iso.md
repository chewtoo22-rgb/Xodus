# Xodus Core ISO — M0 Build

## Pinned source and build path

`upstream/iso.lock` pins pearOS `iso` at `8175d4851fcf85b2325c56a3751c0697e044d049`. `Core ISO Build` fetches that exact Git commit, checks the upstream `build-binary` entrypoint and prebuilt Ploader files, then applies `overlay/apply-xodus-identity.sh` before building. The result is already Xodus-branded; M0 does not build an unmodified pearOS ISO first.

The pinned upstream builder would clone the installer's moving branch into the live image. The Xodus overlay replaces that one audited clone command with a fetch and detached checkout of the commit in `upstream/installer.lock`, then verifies both the commit and its `system_install/setup` blob. A changed upstream command stops the build. This pins the embedded installer source, while package repository and other asset inputs remain subject to the limits below.

The workflow runs on an Ubuntu GitHub runner but invokes the upstream Arch-native builder inside a privileged `archlinux:base-devel` container. It installs the required Arch build tools, initializes repository trust for the package sources used by the ISO profile, and calls `./build-binary --build --filename Xodus-reference --compression fastest --clean --sha256`. The `reference` string is a legacy output filename and artifact label; it does not mean the image is unmodified pearOS. The build uses the prebuilt Ploader artifacts from the pinned source rather than rebuilding that bootloader.

## Artifact and provenance contract

A successful `Core ISO Build` run uploads `xodus-reference-iso-<upstream-sha>` for seven days. The artifact contains the `Xodus-reference-*.iso`, `xodus-reference.sha256`, and a schema-2 `xodus-reference.manifest` with the Xodus source commit, upstream ISO commit, embedded installer commit, filename, and ISO digest. The same three commits are recorded inside the live image's `build-info`. The workflow also packages `xodus-build-attempt-*.log` from successful runs; the M0 completion artifact below included this successful build log. Failed runs upload available attempt logs and disk diagnostics as `xodus-core-iso-failure-diagnostics`, also retained for seven days.

The checksum detects a changed download, and the manifest identifies the source revisions. Neither proves a bitwise reproducible build. The `archlinux:base-devel` tag is not pinned to an immutable digest, and `pacman -Syu` plus the ISO profile resolve packages from rolling repositories and mirrors. A later reproducibility milestone must lock or snapshot those inputs, control build metadata, and compare independently built ISO hashes before claiming identical bytes.

## M0 evidence sequence

1. `Core ISO Build` succeeds on the current `main` commit and uploads the ISO, checksum, manifest, and successful attempt log.
2. `QA QEMU Boot Smoke` downloads that exact Core run's artifact, verifies its checksum, and boots it with OVMF. Its guest probe emits the exact serial line `XODUS_LIVE_DESKTOP_READY` only after finding the live Arch root, active display manager, an active local `liveuser` graphical session (Wayland with `kwin_wayland` or X11 with `kwin_x11`), and `plasmashell`. QA requires that line **and** a fresh QMP framebuffer capture with visible, varied pixels before the boot deadline. It retains `qa-artifacts/serial.log`, `smoke-summary.txt`, `frame-evidence.txt`, `guest-screen-ready.ppm`, periodic VM screenshots/status, and `qa-image-digest.txt` in `xodus-qemu-smoke-<source-sha>`. The pixel check rejects blank screens; it does not recognize the desktop UI, so review the retained frame before qualifying hardware. The older watchdog-only test merely showed that QEMU survived its timeout.
3. `Hardware Candidate Gate` checks successful Core and QA runs and unexpired artifacts for the same current `main` SHA, then publishes `hardware-candidate-<source-sha>`. No historical survival-only QA run is sufficient for the changed gate's new SHA.

The complete sequence passed for the main revision recorded below. Every later candidate needs fresh evidence for its own source revision. The hardware qualification manifest permits a separately controlled **live-boot** test; it does not prove physical installation or recovery/rollback.

## M0 completion record

The M0 live-image VM gate was achieved on 2026-09-28 at `main` commit `bf7e4d41e8107a947aeed5e790b05630bfc61c6f`. All three runs succeeded for that exact source SHA.

| Evidence | Successful run | Artifact ID |
| --- | --- | --- |
| Core ISO, checksum, schema-2 provenance, successful build log | [36490232271](https://github.com/chewtoo22-rgb/Xodus/actions/runs/36490232271) | `11001398667` |
| Strict QEMU desktop readiness and reviewed frame | [36491257156](https://github.com/chewtoo22-rgb/Xodus/actions/runs/36491257156) | `11001945269` |
| Live-boot-only qualification manifest | [36492042191](https://github.com/chewtoo22-rgb/Xodus/actions/runs/36492042191) | `11001765855` |

The ISO SHA-256 is `a43ee6ab504be28f75398015b6a7105bec68a0c546a7d38786e4ed414a6726f6`. Core and QA recorded the same digest, and the candidate manifest bound that image to the Core and QA run/artifact IDs. The upstream ISO pin was `8175d4851fcf85b2325c56a3751c0697e044d049`; the embedded installer pin was `e676698b4a07f797a50fd25241a738ead75248e6`.

QA reached `XODUS_LIVE_DESKTOP_READY` and retained a fresh visible frame at 49 seconds. Manual review confirmed the Plasma desktop, Welcome window, calendar, and wallpaper. The evidence ZIPs were downloaded and their archive digests verified. QA checksum-verified the full 5 GB ISO; local review used the retained evidence without downloading the ISO again.

At review, the Core and QA artifacts were unexpired with retention through 2026-10-05, and the candidate manifest through 2026-10-12. Artifact expiry does not undo the recorded milestone, but an expired artifact cannot qualify a later hardware candidate.

This record establishes the live-image VM milestone. Physical live boot, physical installation and recovery/rollback, bitwise reproducibility, redistribution clearance, and the full M1 graphical rebrand remain unfinished.

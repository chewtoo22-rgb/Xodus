# Xodus Core ISO — M0 Build

## Pinned source and build path

`upstream/iso.lock` pins pearOS `iso` at `8175d4851fcf85b2325c56a3751c0697e044d049`. `Core ISO Build` fetches that exact Git commit, checks the upstream `build-binary` entrypoint and prebuilt Ploader files, then applies `overlay/apply-xodus-identity.sh` before building. The result is already Xodus-branded; M0 does not build an unmodified pearOS ISO first.

The workflow runs on an Ubuntu GitHub runner but invokes the upstream Arch-native builder inside a privileged `archlinux:base-devel` container. It installs the required Arch build tools, initializes repository trust for the package sources used by the ISO profile, and calls `./build-binary --build --filename Xodus-reference --compression fastest --clean --sha256`. The `reference` string is a legacy output filename and artifact label; it does not mean the image is unmodified pearOS. The build uses the prebuilt Ploader artifacts from the pinned source rather than rebuilding that bootloader.

## Artifact and provenance contract

A successful `Core ISO Build` run uploads `xodus-reference-iso-<upstream-sha>` for seven days. The artifact contains the `Xodus-reference-*.iso`, `xodus-reference.sha256`, and `xodus-reference.manifest` with the Xodus source commit, upstream commit, filename, and ISO digest. The workflow also packages `xodus-build-attempt-*.log` from successful runs; confirm the log is present in the first fresh artifact after this workflow change. Failed runs upload available attempt logs and disk diagnostics as `xodus-core-iso-failure-diagnostics`, also retained for seven days.

The checksum detects a changed download, and the manifest identifies the source revisions. Neither proves a bitwise reproducible build. The `archlinux:base-devel` tag is not pinned to an immutable digest, and `pacman -Syu` plus the ISO profile resolve packages from rolling repositories and mirrors. A later reproducibility milestone must lock or snapshot those inputs, control build metadata, and compare independently built ISO hashes before claiming identical bytes.

## M0 evidence sequence

1. `Core ISO Build` succeeds on the current `main` commit and uploads the ISO, checksum, manifest, and successful attempt log.
2. `QA QEMU Boot Smoke` downloads that exact Core run's artifact, verifies its checksum, and boots it with OVMF. Its guest probe emits the exact serial line `XODUS_LIVE_DESKTOP_READY` only after finding the live Arch root, active display manager, an active local `liveuser` graphical session (Wayland with `kwin_wayland` or X11 with `kwin_x11`), and `plasmashell`. QA requires that line and retains `qa-artifacts/serial.log`, `smoke-summary.txt`, VM diagnostics, and `qa-image-digest.txt` in `xodus-qemu-smoke-<source-sha>`. A screen dump may be captured for diagnosis but is not the pass condition. The older watchdog-only test merely showed that QEMU survived its timeout.
3. `Hardware Candidate Gate` checks successful Core and QA runs and unexpired artifacts for the same current `main` SHA, then publishes `hardware-candidate-<source-sha>`. No historical survival-only QA run is sufficient for the changed gate's new SHA.

M0 exit remains pending until this complete sequence passes on a fresh commit. The hardware qualification manifest permits a separately controlled **live-boot** test; it does not prove physical installation or recovery/rollback.

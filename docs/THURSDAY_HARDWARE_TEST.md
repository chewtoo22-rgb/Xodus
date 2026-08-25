# Thursday Hardware Validation

This runbook is the M0 physical-machine gate for Xodus.

## Candidate rule

Only test an image whose commit has:

1. a successful `Core ISO Build` run,
2. a successful `QA QEMU Boot Smoke` run for the same commit SHA, and
3. a generated `hardware-candidate-<sha>` qualification manifest.

Do not substitute an older ISO, a locally modified image, or an artifact from a different commit.

## Installer safety boundary

The current pearOS Electron installer is explicitly work-in-progress and documents whole-disk destructive behavior. Until Xodus has passed an automated destructive-install test against an expendable virtual disk, **Thursday M0 hardware testing is live-boot-only**.

Do not press the installer's destructive Continue/erase path on a disk containing wanted data. Do not use the 1 TB target SATA disk for installation until the VM installer gate is green.

## USB preparation

### Preferred: verified fetch + guarded writer

On a Linux machine with GitHub CLI (`gh`), `jq`, and `sha256sum` installed and authenticated to GitHub, fetch the exact qualified candidate:

```bash
./scripts/fetch-qualified-candidate.sh
```

The fetcher:

- selects the latest successful `Hardware Candidate Gate` run on `main`,
- downloads its qualification manifest,
- independently re-checks that the Core ISO and QEMU QA runs are successful and use the same commit SHA,
- downloads the exact ISO artifact named by the manifest,
- verifies the producer-provided SHA-256 checksum, and
- preserves `hardware-candidate.json` beside the image.

An optional output directory may be supplied as the first argument.

Before writing anything, identify the dedicated USB disk with `lsblk` and run the guarded writer in dry-run mode:

```bash
./scripts/write-candidate-usb.sh --dry-run xodus-hardware-candidate /dev/sdX
```

Replace `/dev/sdX` with the **whole USB disk**, never a partition such as `/dev/sdX1`. The writer refuses non-disk block devices, mounted targets, the disk backing the running root filesystem, undersized targets, missing candidate provenance, bad checksums, and unexpected candidate policy.

After the dry-run identifies the exact intended USB device, perform the real write:

```bash
./scripts/write-candidate-usb.sh xodus-hardware-candidate /dev/sdX
```

The script displays model, serial, size, candidate SHA, and a destructive-write warning, then requires you to type the exact device path before `dd` is allowed to run. It never auto-unmounts a disk.

### Manual fallback

- Download the exact ISO artifact named in `hardware-candidate.json`.
- Confirm the candidate, Core ISO, and QEMU QA commit SHAs are identical.
- Verify the downloaded ISO using the SHA-256 checksum packaged by the Core ISO build.
- Write the verified ISO only to a dedicated USB drive using a raw-image-capable writer.
- Safely eject the drive after writing.

## Firmware setup

Before booting the USB:

- record the current firmware/BIOS boot settings,
- prefer UEFI boot,
- temporarily disable Secure Boot if the image does not boot with it enabled,
- do not change storage controller mode unless required,
- keep the existing OS disk untouched.

## Live-boot test sequence

Record PASS/FAIL for each item:

- [ ] Xodus USB appears in the UEFI boot menu.
- [ ] Bootloader renders and accepts input.
- [ ] Kernel/initramfs loads without an unrecoverable panic.
- [ ] Graphical session reaches the desktop.
- [ ] Xodus identity is visible rather than pearOS-only identity.
- [ ] Keyboard works.
- [ ] Mouse/touchpad works.
- [ ] Display uses the expected native resolution.
- [ ] Wi-Fi adapter is detected.
- [ ] Wi-Fi can associate and reach the internet.
- [ ] Ethernet is detected if connected.
- [ ] Bluetooth controller is present and can be enabled.
- [ ] Audio output device is detected.
- [ ] Audio playback works.
- [ ] Suspend/resume completes once without a hard lock.
- [ ] Reboot/shutdown completes cleanly.
- [ ] Existing installed OS remains bootable after USB removal.

## Evidence to capture

For every failure, record:

- candidate commit SHA,
- machine model,
- firmware/BIOS version if readily visible,
- failing checklist item,
- exact visible error text,
- a photo/screenshot when practical,
- whether the failure reproduces after one cold reboot.

If the live system reaches a terminal, also capture:

```bash
uname -a
lspci -nnk
lsusb
ip link
rfkill list
inxi -Fazy 2>/dev/null || true
journalctl -b -p warning..alert --no-pager
```

## Stop conditions

Stop physical testing and return to VM/CI if any of these occur:

- storage device names look ambiguous,
- the installer presents only whole-disk erase for a disk with wanted data,
- kernel panic repeats,
- the boot process writes unexpectedly to an internal disk,
- firmware settings cannot be restored confidently.

## M0 hardware pass

M0 is hardware-validated when the candidate completes live boot, input, display, network, audio, one suspend/resume cycle, and clean shutdown/reboot without modifying an internal disk.

Installation becomes a separate gate after destructive installer behavior is proven against an expendable QEMU disk and post-install boot is automated.

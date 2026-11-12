# Thursday Hardware Validation

This runbook covers physical **live boot** of an M0 image. Installation to an internal disk is a separate, currently blocked gate.

## Candidate rule

Only test an image whose commit is the current `main` HEAD and has:

1. a successful `Core ISO Build` run,
2. a successful updated `QA QEMU Boot Smoke` run for the same commit SHA, with retained positive graphical-session evidence, and
3. an unexpired `hardware-candidate-<sha>` qualification manifest tying those same-commit ISO and QA artifacts together.

The former QEMU watchdog pass only proved the VM did not exit early. It is not desktop evidence. After the new gate lands, require a fresh Core/QA chain on that `main` commit; do not substitute an older ISO, a locally modified image, or an artifact from a different commit. Confirm the Core artifact includes its checksum, provenance manifest, and successful build log before writing USB media. In `xodus-qemu-smoke-<source-sha>`, check `qa-artifacts/smoke-summary.txt` for `result=pass`, `guest_evidence=XODUS_LIVE_DESKTOP_READY`, and `rendered_frame=guest-screen-ready.ppm`; check `qa-artifacts/serial.log` for the exact guest sentinel. Review `guest-screen-ready.ppm` to confirm it shows the desktop, since the automated pixel check establishes only that the frame is not blank. `qa-image-digest.txt` records the ISO checksum and Core run ID.

The manifest policy must be `live-boot-only`. A passing VM installer gate does not change that policy or authorize physical installation; the recovery/rollback and dedicated-disk requirements below still apply.

## Installer safety boundary

The pearOS Electron installer is whole-disk destructive. Historical automated destructive-install runs passed on an expendable virtual disk: the exact audited installer completed, installer media was detached, the installed GPT/ESP/root layout was verified, OVMF booted the installed disk independently, and installed userspace emitted the exact `XODUS_POSTINSTALL_BOOT_OK` sentinel.

That automated proof does **not** count as physical NUC/SATA validation or recovery/rollback proof. Thursday begins and ends with the live-boot checklist while the separate recovery/rollback gate remains open. Physical installation later requires a fresh destructive VM result for the candidate, an acceptable live-boot checklist, a tested recovery/rollback procedure, a dedicated disk containing no wanted data, and `scripts/installer-target-guard.sh` approval of that exact whole-disk device after explicit human opt-in.

Never use an ambiguous device name, a mounted disk, the disk backing the running system, or a disk containing wanted data.

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
Use the authenticated fetcher's output for the guarded writer. The writer's
`--verify-bundle` mode checks that the local manifest, producer manifest,
checksum, and ISO agree; those files alone cannot authenticate a qualification
run or prove that the commit is still current `main`.

Before writing anything, identify the dedicated USB disk with `lsblk` and run the guarded writer in dry-run mode:

```bash
./scripts/write-candidate-usb.sh --dry-run xodus-hardware-candidate /dev/sdX
```

Replace `/dev/sdX` with the **whole USB disk**, never a partition such as `/dev/sdX1`. The writer refuses non-disk block devices, mounted targets, disks backing the running root filesystem, undersized targets, inconsistent bundle files, and unexpected candidate policy. It checks the target again immediately before writing, including when `--yes` skips typed confirmation, and aborts if its identity has changed.

After the dry-run identifies the exact intended USB device, perform the real write:

```bash
./scripts/write-candidate-usb.sh xodus-hardware-candidate /dev/sdX
```

The script displays model, serial, size, candidate SHA, and a destructive-write warning, then requires you to type the exact resolved device path before `dd` is allowed to run. It never auto-unmounts a disk.

### Manual fallback

- Download the exact ISO artifact named in `hardware-candidate.json`.
- Confirm the candidate, Core ISO, and updated graphical QEMU QA commit SHAs are identical and equal current `main`.
- Verify the downloaded ISO using the SHA-256 checksum packaged by the Core ISO build.
- Confirm the QA evidence contains a positive desktop-session result; the older watchdog-only summary is insufficient.
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

## Future physical install gate — blocked pending recovery/rollback proof

Do not enter this section merely because the VM gate or live-boot checklist is green. First capture the live-boot evidence, rerun the destructive VM install gate for the intended candidate, and verify a documented recovery/rollback procedure on an expendable disk. Until that recovery/rollback proof exists, stop after live boot and leave internal disks unchanged.

If physical installation is intentionally being tested, use only a dedicated target disk with **no wanted data**. Identify the whole-disk device and record its model, serial, and size:

```bash
lsblk -d -o NAME,MODEL,SERIAL,SIZE,TYPE
```

Then run the read-only target guard with both explicit confirmations:

```bash
export XODUS_ALLOW_PHYSICAL_INSTALL=YES-I-UNDERSTAND
export XODUS_INSTALL_CONFIRM=/dev/sdX
bash scripts/installer-target-guard.sh /dev/sdX
```

Replace `/dev/sdX` with the exact dedicated installation disk. A guard refusal is a **STOP**, not an invitation to bypass the check.

Before pressing any destructive installer confirmation, re-read the device model/serial/size and confirm that the target contains no wanted data. Disconnect unrelated removable storage when practical. Do not install to the current OS disk as part of the first physical Xodus install test.

After installation:

- remove the installer USB before the first installed-disk boot,
- boot the installed target through UEFI,
- verify the Xodus/Arch bootloader reaches the installed system,
- verify keyboard, display, network, audio, and clean reboot/shutdown again from the installed system,
- record the installed target model/serial and all failures,
- do not call the hardware install path PASS until the installed disk has booted independently without installer media.

## Evidence to capture

As soon as the live system reaches a terminal, run the read-only collector shipped inside the qualified Xodus image:

```bash
/usr/lib/xodus/xodus-hardware-live-evidence xodus-hardware-evidence
```

The collector obtains the candidate SHA directly from the image's `/usr/lib/xodus/build-info`, so this step does not require a Git checkout, network access, or a manually supplied SHA. Keep the resulting `xodus-hardware-evidence/` directory with the candidate qualification manifest. The collector records OS/kernel identity, block and mount topology, PCI/USB devices, networking, rfkill/Bluetooth/audio state, UEFI status, failed units, and boot warnings. It is observational only; CI rejects destructive storage commands in the collector source and verifies that the exact collector is installed into the produced payload.

For every failure, additionally record:

- candidate commit SHA,
- machine model,
- firmware/BIOS version if readily visible,
- failing checklist item,
- exact visible error text,
- a photo/screenshot when practical,
- whether the failure reproduces after one cold reboot.

If the shipped collector cannot be run, capture the minimum fallback manually:

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
- the target guard refuses the proposed installation disk,
- the installer presents a different target than the exact disk that was preflighted,
- the proposed target contains wanted data,
- kernel panic repeats,
- the boot process writes unexpectedly to an internal disk,
- firmware settings cannot be restored confidently.

## Live hardware pass

Live hardware validation passes when the candidate completes live boot, input, display, network, audio, one suspend/resume cycle, and clean shutdown/reboot without modifying an internal disk.

Physical installation is a separate result. It passes only after the recovery/rollback prerequisite and live-boot gate are acceptable, the exact dedicated target passes `installer-target-guard.sh`, installation completes, installer media is removed, and that physical installed disk boots independently under UEFI. Until those steps are performed and recovery is verified on real hardware, no NUC/SATA installation or rollback success is claimed.

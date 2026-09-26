# Xodus Roadmap

## M0 — First Blood
Goal: prove that a source-pinned, Xodus-branded live image reaches the NiceC0re desktop in a VM, with inspectable build and boot evidence.

- [x] Initialize Xodus integration repository.
- [x] Define upstream-layer architecture.
- [x] Pin the pearOS ISO source revision in `upstream/iso.lock` and add upstream sync tooling.
- [x] Add repository validation and source-contract CI.
- [x] Apply the minimum Xodus identity overlay before building the ISO.
- [x] Build a branded ISO in `Core ISO Build` and package its SHA-256 and source provenance. Historical runs passed; this change needs a fresh run.
- [x] Launch that ISO under QEMU/OVMF in `QA QEMU Boot Smoke`. The historical watchdog pass proves only that QEMU did not exit early.
- [ ] Capture a positive graphical-session signal and retain its VM evidence from the updated QA gate on the current `main` commit.
- [ ] Retain the successful ISO build log with that commit's ISO artifact and confirm the fresh artifact is downloadable and checksum-valid.

**Exit gate:** the current `main` commit has successful, matching-commit Core ISO and updated QA runs. The ISO artifact contains the image, checksum, source provenance, and successful build log. QA evidence positively shows the desktop session started; a watchdog timeout alone cannot pass. `Hardware Candidate Gate` must then produce a qualification manifest for that same current commit. An older green run or artifact is not M0 completion evidence.

This is a **live-image VM gate**. Physical live boot on an Intel NUC is a later, separate observation. Physical installation needs the destructive VM installer proof, a dedicated empty target, an explicit human decision, and a verified recovery/rollback procedure. No physical install or rollback success is claimed here. Pinning the pearOS Git revision gives source provenance, but the Arch container tag and rolling package repositories are not locked, so M0 does not claim byte-for-byte reproducible ISOs.

## M1 — Identity
- Xodus boot identity and Plymouth.
- Login/lock experience.
- Desktop theme, icon strategy, wallpaper system.
- Dock/control center/notch behavior.
- System About page and release metadata.

## M2 — Safe Install + Recovery
- Installer safety review.
- Maintain automatic destructive-install proof on an expendable VM disk and verify installed-disk UEFI/userspace boot.
- BTRFS snapshot/rollback design where supported.
- Recovery boot entry and repair tools.
- Update transaction + rollback policy.

## M3 — Gaming Core
- Steam + Proton integration.
- Wine/Bottles optional stack.
- GameMode/performance profiles.
- Controller-first launcher mode.
- Emulator manager architecture.

## M4 — Xodus Agent
- Unprivileged desktop assistant.
- Local tool registry.
- Privileged broker with typed operations.
- Audit log and permission UI.
- System diagnostics and package-management skills.

## M5 — Hardware Candidate
Target: x86-64 Intel NUC test machine.

- Intel graphics/audio/network validation.
- Suspend/resume.
- Bluetooth/controller testing.
- Installation to dedicated target disk.
- Recovery and rollback drills.

## M6 — Daily Driver Beta
- Harden updater.
- Crash/report tooling without mandatory telemetry.
- Performance profiling.
- Accessibility pass.
- Documentation and recovery guide.

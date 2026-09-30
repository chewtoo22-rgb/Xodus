# Xodus Roadmap

## M0 — First Blood
Goal: prove that a source-pinned, Xodus-branded live image reaches the NiceC0re desktop in a VM, with inspectable build and boot evidence.

- [x] Initialize Xodus integration repository.
- [x] Define upstream-layer architecture.
- [x] Pin the pearOS ISO source revision in `upstream/iso.lock` and add upstream sync tooling.
- [x] Add repository validation and source-contract CI.
- [x] Apply the minimum Xodus identity overlay before building the ISO.
- [x] Build a branded ISO in `Core ISO Build` and package its SHA-256 and source provenance.
- [x] Launch that exact ISO under QEMU/OVMF in `QA QEMU Boot Smoke` and verify its checksum.
- [x] Capture a positive graphical-session signal and a fresh visible VM frame from the strict QA gate on the same `main` commit; review the retained frame.
- [x] Retain the successful ISO build log with that commit's ISO artifact and verify matching artifact and image digests through the Core/QA evidence.
- [x] Produce a matching-source qualification manifest with `Hardware Candidate Gate`.

**Achieved on 2026-09-28:** `main` commit `bf7e4d41e8107a947aeed5e790b05630bfc61c6f` passed Core run `36490232271`, QA run `36491257156`, and candidate run `36492042191`. The reviewed QA frame showed the running Plasma desktop. The [completion record](core-iso.md#m0-completion-record) lists the artifact IDs and ISO digest. Full graphical rebranding remains M1 work.

**Exit gate:** the current `main` commit has successful, matching-commit Core ISO and updated QA runs. The ISO artifact contains the image, checksum, source provenance, and successful build log. QA evidence shows the guest desktop session started and includes a fresh visible QMP frame; a watchdog timeout or process-only signal cannot pass. Review the frame before hardware qualification. `Hardware Candidate Gate` must then produce a qualification manifest for that same current commit. An older green run or artifact is not M0 completion evidence.

This is a **live-image VM gate**. Physical live boot on an Intel NUC is a later, separate observation. Physical installation needs the destructive VM installer proof, a dedicated empty target, an explicit human decision, and a verified recovery/rollback procedure. No physical install or rollback success is claimed here. Pinning the pearOS Git revision gives source provenance, but the Arch container tag and rolling package repositories are not locked, so M0 does not claim byte-for-byte reproducible ISOs.

## M1 — Identity

Goal: complete the graphical redesign with a consistent Xodus identity across every user-facing surface. M1 is in progress; these items remain open until the staged ISO and runtime evidence verify them.

- [ ] Use the user's new boot video as the retained master and derive the graphical boot sequence for Plymouth; update firmware/boot menus and splash assets.
- [ ] Redesign login, lock, and desktop-session splash screens.
- [ ] Apply the Xodus desktop theme, icon strategy, wallpapers, menus, dock, control center, and notch.
- [ ] Replace the upstream Welcome UI and its application/autostart entries with Xodus Welcome.
- [ ] Rebrand the compiled settings UI, System About app, release metadata, and their visible logos/text.
- [ ] Rebrand the installer frontend and installation/recovery entry points.
- [ ] Inspect the staged image for residual user-facing pearOS branding, preserve upstream license/attribution notices, and retain runtime screenshots of the redesigned surfaces.
- [ ] Pass fresh Core ISO, strict QEMU desktop, and candidate gates for the completed M1 source revision.

**Exit gate:** review the boot, login/lock, desktop shell, Welcome, settings/About, and installer interfaces from the produced image, with consistent Xodus branding across all of them.

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

# Xodus Roadmap

## M0 — First Blood
Goal: prove the foundation can be reproduced and safely evolved.

- [x] Initialize Xodus integration repository.
- [x] Define upstream-layer architecture.
- [ ] Pin initial pearOS upstream revisions.
- [ ] Add upstream sync tooling.
- [ ] Add repository validation CI.
- [ ] Build first unmodified-reference ISO in CI.
- [ ] Apply minimum Xodus identity overlay.
- [ ] Boot ISO in QEMU/OVMF.
- [ ] Archive ISO and smoke-test logs as Actions artifacts.

Exit gate: a reproducible Xodus-branded ISO boots to the NiceC0re desktop in a VM.

## M1 — Identity
- Xodus boot identity and Plymouth.
- Login/lock experience.
- Desktop theme, icon strategy, wallpaper system.
- Dock/control center/notch behavior.
- System About page and release metadata.

## M2 — Safe Install + Recovery
- Installer safety review.
- Automatic VM destructive-install tests.
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

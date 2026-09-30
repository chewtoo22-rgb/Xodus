# Xodus

> An AI-first, gaming-capable desktop operating system built on an Arch Linux / pearOS NiceC0re foundation.

## Status

**M0 — First Blood: live-image VM gate achieved. M1 graphical redesign is in progress.**

Xodus begins with the parts pearOS already does well: a polished KDE/Wayland desktop, installer and ISO tooling, system settings, visual effects, and a cohesive desktop experience. From there, Xodus will progressively replace pearOS identity and add its own system intelligence, gaming stack, recovery/update model, and desktop UX.

The M0 live-image gate passed on `main` commit `bf7e4d41e8107a947aeed5e790b05630bfc61c6f`: [Core ISO Build](https://github.com/chewtoo22-rgb/Xodus/actions/runs/36490232271), [QA QEMU Boot Smoke](https://github.com/chewtoo22-rgb/Xodus/actions/runs/36491257156), and [Hardware Candidate Gate](https://github.com/chewtoo22-rgb/Xodus/actions/runs/36492042191) all succeeded for that source revision. QA verified the ISO checksum, observed the desktop readiness signal, and retained a fresh frame that was reviewed. The qualification is **live-boot-only**. See the [M0 evidence record](docs/core-iso.md#m0-completion-record) and [remaining roadmap](docs/ROADMAP.md).

M1 must replace the remaining visible pearOS identity across the graphical boot sequence, login and lock screens, desktop shell, Welcome, settings, About, and installer. The supplied new boot video is the boot reference. This full redesign remains unfinished.

## Goals

- Preserve a polished desktop experience while creating a distinct Xodus identity.
- Keep the Arch Linux rolling-release foundation.
- Maintain upstream pearOS as a reference/upstream layer instead of creating an unmergeable one-off fork.
- Build traceable bootable ISOs in GitHub Actions, then lock the remaining inputs needed for bitwise reproducibility.
- Add an AI system agent with explicit permissions and auditable actions.
- Add first-class gaming, controller, Proton/Wine, and emulator support.
- Build safe installation, rollback, recovery, and update paths before physical installation testing.
- Target the Intel NUC / x86-64 PC platform first.

## Architecture

Xodus is organized as an integration repository. Upstream pearOS components are tracked independently and Xodus-specific changes live as overlays, packages, configuration, branding, and patches.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Upstream components under evaluation

- `pearOS-archlinux/iso`
- `pearOS-archlinux/filesystem`
- `pearOS-archlinux/pkgbuilds`
- `pearOS-archlinux/pearOS-installer`
- `pearOS-archlinux/pear-calamares-config`
- `pearOS-archlinux/pearos-settings`
- `pearOS-archlinux/liquid-gel`
- `pearOS-archlinux/pearos-bootloader`
- `pearOS-archlinux/pearos-apps-bundle`
- `pearOS-archlinux/artwork`
- `pearOS-archlinux/pearos-sounds`

## Workstreams

1. **Core OS / ISO** — upstream sync, packages, kernel, filesystem, traceable ISO builds.
2. **Desktop / UX** — Xodus shell identity, dock, settings, lock screen, control center, visual effects.
3. **AI System Agent** — local/remote model routing, system tools, permissions, audit log.
4. **Gaming** — Proton/Wine/Bottles, controllers, emulation, performance profiles.
5. **Installer / Recovery** — safe partitioning, rollback, recovery image, upgrade paths.
6. **QA / CI** — static checks, package validation, ISO builds, VM boot/install smoke tests.

## Licensing

Xodus will preserve all applicable upstream licenses, notices, source obligations, and attribution. Components will be reviewed individually before redistribution; no assumption is made that every asset or component shares the same license.

## Release blockers

A public release is not cleared. The full graphical redesign is unfinished; [upstream component licensing and redistribution review](docs/UPSTREAM_REDISTRIBUTION_REVIEW.md) is open; the Arch container and rolling package inputs are not locked for bitwise reproducibility; and physical live boot, installation, and recovery/rollback have not been validated on the target hardware. Each new candidate source revision must pass fresh build, QA, and qualification gates.

---

**Xodus M0 objective:** produce a source-pinned, branded Xodus ISO with retained build and VM evidence that proves the NiceC0re desktop starts. This is a live-image milestone. Physical installation and recovery/rollback require separate gates.

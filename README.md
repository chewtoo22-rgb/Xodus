# Xodus

> An AI-first, gaming-capable desktop operating system built on an Arch Linux / pearOS NiceC0re foundation.

## Status

**M0 — First Blood: desktop boot proof pending**

Xodus begins with the parts pearOS already does well: a polished KDE/Wayland desktop, installer and ISO tooling, system settings, visual effects, and a cohesive desktop experience. From there, Xodus will progressively replace pearOS identity and add its own system intelligence, gaming stack, recovery/update model, and desktop UX.

The pearOS ISO source is pinned, the Xodus identity overlay is applied before the Arch build, and GitHub Actions builds an ISO and runs QEMU/OVMF QA. Earlier matching-commit green runs establish that the pipeline has built an image and kept a VM running; the old QEMU watchdog did not prove that a graphical desktop appeared. M0 remains open until a fresh build and QA run on the current `main` commit retain evidence of the desktop session. See the [M0 gate](docs/ROADMAP.md) and [ISO build notes](docs/core-iso.md).

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

A public release is not cleared. The graphical VM boot gate still needs a fresh passing artifact; [upstream component licensing and redistribution review](docs/UPSTREAM_REDISTRIBUTION_REVIEW.md) is open; the Arch container and rolling package inputs are not locked for bitwise reproducibility; and physical live boot, installation, and recovery/rollback have not been validated on the target hardware.

---

**Xodus M0 objective:** produce a source-pinned, branded Xodus ISO with retained build and VM evidence that proves the NiceC0re desktop starts. This is a live-image milestone. Physical installation and recovery/rollback require separate gates.

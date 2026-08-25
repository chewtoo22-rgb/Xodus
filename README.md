# Xodus

> An AI-first, gaming-capable desktop operating system built on an Arch Linux / pearOS NiceC0re foundation.

## Status

**M0 — First Blood: bootstrap in progress**

Xodus begins with the parts pearOS already does well: a polished KDE/Wayland desktop, installer and ISO tooling, system settings, visual effects, and a cohesive desktop experience. From there, Xodus will progressively replace pearOS identity and add its own system intelligence, gaming stack, recovery/update model, and desktop UX.

## Goals

- Preserve a polished desktop experience while creating a distinct Xodus identity.
- Keep the Arch Linux rolling-release foundation.
- Maintain upstream pearOS as a reference/upstream layer instead of creating an unmergeable one-off fork.
- Build reproducible bootable ISOs in GitHub Actions.
- Add an AI system agent with explicit permissions and auditable actions.
- Add first-class gaming, controller, Proton/Wine, and emulator support.
- Build safe installation, rollback, recovery, and update paths before hardware testing.
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

1. **Core OS / ISO** — upstream sync, packages, kernel, filesystem, reproducible ISO.
2. **Desktop / UX** — Xodus shell identity, dock, settings, lock screen, control center, visual effects.
3. **AI System Agent** — local/remote model routing, system tools, permissions, audit log.
4. **Gaming** — Proton/Wine/Bottles, controllers, emulation, performance profiles.
5. **Installer / Recovery** — safe partitioning, rollback, recovery image, upgrade paths.
6. **QA / CI** — static checks, package validation, ISO builds, VM boot/install smoke tests.

## Licensing

Xodus will preserve all applicable upstream licenses, notices, source obligations, and attribution. Components will be reviewed individually before redistribution; no assumption is made that every asset or component shares the same license.

---

**Xodus M0 objective:** produce the first reproducible, branded Xodus ISO that boots in a VM without losing the core NiceC0re desktop experience.

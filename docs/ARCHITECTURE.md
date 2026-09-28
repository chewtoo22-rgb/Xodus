# Xodus Architecture

## Design rule

Xodus is an integration layer over upstream projects, not a permanently diverged monolith. Upstream pearOS repositories are treated as vendor sources. Xodus-owned behavior lives in overlays, packages, patches, workflows, branding, and services that can be reviewed independently.

## Layers

### 1. Upstream
Tracks selected pearOS NiceC0re components and Arch Linux dependencies.

### 2. Vendor cache
Checked-out upstream sources used by CI and local builds. Vendor sources are never the canonical home of Xodus-specific features.

### 3. Xodus overlay
Branding, configuration, package manifests, desktop defaults, services, hooks, and patch queues.

### 4. Xodus services
System agent, permission broker, gaming/performance services, updater, recovery tooling, diagnostics, and telemetry-free local audit logs.

### 5. Distribution
ISO composition, installer configuration, bootloader, recovery environment, and release metadata.

## Initial component map

| Area | Upstream reference | Xodus ownership |
| --- | --- | --- |
| ISO composition | pearOS-archlinux/iso | build orchestration, Xodus packages and release metadata |
| Base filesystem | pearOS-archlinux/filesystem | identity, defaults, system policy |
| Packages | pearOS-archlinux/pkgbuilds | Xodus packages and patch queue |
| Installer | pinned pearOS-archlinux/pearOS-installer setup; pear-calamares-config under evaluation | payload handoff, target guard, VM install proof, physical safety gates |
| Settings | pearOS-archlinux/pearos-settings | Xodus settings pages and system integrations |
| Effects | pearOS-archlinux/liquid-gel | visual tuning and Xodus UX |
| Boot | pearOS-archlinux/pearos-bootloader + plymouth | Xodus boot identity and recovery entries |
| Desktop apps | pearOS-archlinux/pearos-apps-bundle | selective reuse/replacement |

## Multi-agent ownership

Each workstream owns a directory and must avoid editing another workstream's files without an integration PR.

- `core/` — Core OS agent
- `desktop/` — Desktop/UX agent
- `agent/` — AI system-agent workstream
- `gaming/` — Gaming workstream
- `installer/` — Installer/recovery workstream
- `qa/` — QA and test workstream
- `vendor/` — generated upstream checkout area, ignored by git
- `scripts/` — shared build/sync tooling; changes require integration review

## Security model for the AI agent

The AI layer must not run as unrestricted root. Privileged actions pass through a narrow broker with explicit verbs, typed arguments, policy checks, user confirmation for destructive operations, and an audit log. Model output is never executed directly as shell code by the privileged service.

## Live-image and installation gates

A **live-boot-only** hardware candidate needs validated manifests and configuration, pinned upstream source, a successful ISO build, and positive VM evidence that the desktop session starts. `Hardware Candidate Gate` must bind the Core ISO and QA runs and unexpired artifacts to the same current `main` commit. The former QEMU watchdog result alone did not establish a usable desktop.

Physical installation is a separate gate. The expendable-disk destructive VM workflow and detached-media post-install UEFI/userspace proof exercise the installer path, but they do not prove safety on a real disk. Before a physical install trial, the live hardware checklist must pass, a dedicated empty target must be identified and accepted by the read-only target guard, and a recovery/rollback procedure must be defined and verified. Installed-disk boot and recovery must then be checked on the target machine before either is claimed successful.

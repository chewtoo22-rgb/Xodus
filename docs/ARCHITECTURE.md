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
| Installer | pearOS-archlinux/pearOS-installer + pear-calamares-config | branding, safety gates, target profiles |
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

## Release gates

A candidate release cannot progress to hardware testing until:

1. manifests validate;
2. upstream sources resolve to known commits;
3. configuration checks pass;
4. ISO builds successfully;
5. VM boots successfully;
6. installer completes in an expendable VM disk;
7. post-install smoke tests pass;
8. rollback/recovery path is verified.

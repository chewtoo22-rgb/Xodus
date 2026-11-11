# Xodus Studio

Xodus Studio is the opt-in game and app development layer. It turns an Xodus desktop into a game-dev workstation without making the ISO heavier: nothing in Studio ships by default, and every package comes from the official Arch `core` and `extra` repositories.

## Principles

- **Opt-in, never in the ISO.** `iso_default` is pinned to `false` by contract. The live image stays lightweight; Studio is installed after first boot when the user asks for it.
- **Official repositories only.** No AUR, no curl-to-shell installers, no vendored binaries. A weekly CI job checks that every package still resolves in `core`/`extra` on the rolling Arch repos.
- **Plan, then confirm.** `scripts/xodus-studio-plan.py` produces a deterministic, non-executing plan (exact `pacman` argv). A future permission-gated installer, the same broker model the AI agent uses, shows the plan and runs it only after user confirmation.
- **Same hardware policy as the system assistant.** The `ai-assist` profile reuses `scripts/xodus-ai-select.py`, so the local coding assistant obeys the same RAM/VRAM tiers and is disabled on machines that cannot run it responsively.
- **Desktop session only.** Studio tools live in the normal desktop session. Arena Mode remains the place to *play*; a Studio "playtest in Arena" action is a later integration point.

## Profiles

Profiles are defined in [`studio/xodus-studio-manifest.json`](../studio/xodus-studio-manifest.json). `requires` is expanded transitively.

| Profile | Requires | Contents |
| --- | --- | --- |
| `toolchain` | none | base-devel, git, clang, cmake, ninja, meson, pkgconf, gdb, python, rust |
| `graphics` | toolchain | Vulkan headers/loader/validation layers/tools, glslang, shaderc, spirv-tools, SDL3, mesa-utils, plus the Vulkan driver for each detected GPU (Intel `vulkan-intel`, AMD `vulkan-radeon`, NVIDIA `nvidia-utils`) |
| `engines` | graphics | Godot, LÖVE, raylib |
| `editor` | none | Code - OSS (`code`) |
| `art` | none | Blender, Krita, GIMP, Inkscape |
| `audio` | none | Audacity, LMMS |
| `profiling` | graphics | RenderDoc, perf, Valgrind, MangoHud |
| `ai-assist` | editor | Local Xodus model as an offline coding assistant (no extra packages; uses the AI runtime) |

## Usage

```sh
scripts/xodus-studio-plan.py --list
scripts/xodus-studio-plan.py --profile engines --profile art --gpu-vendor amd
scripts/xodus-studio-plan.py --profile ai-assist --gpu-vendor intel --ram-gib 16 --cpu-threads 8
```

The output is JSON with the resolved profiles, package set, `pacman -S --needed --` argv, AI assistant tier, and warnings. `executed` and `network_used` are always `false`.

## Local AI coding assistant

The coding assistant is the Tier 1/Tier 2 local model from [`AI_MODEL_STACK.md`](AI_MODEL_STACK.md), exposed to the editor through the local llama.cpp server (OpenAI-compatible HTTP on localhost). It runs unprivileged, works offline, and never executes code on its own. Suggestions are text the user accepts. When Arena Mode needs the GPU, the model yields like any other local AI workload.

## Roadmap (M7)

1. Manifest, contract, and planner (this change).
2. `xodus-studio` desktop app: profile picker, plan preview, confirm, install through the privileged broker, audit-log entry.
3. Project templates: Godot 2D/3D, SDL3 + Vulkan (C/C++), raylib, Rust; each builds out of the box and has a CI smoke build.
4. Editor integration for the local assistant (endpoint config, model tier display, offline indicator).
5. "Playtest in Arena": launch the current project in an Arena gamescope session with the overlay on.
6. Hardware validation on the Intel NUC target: Vulkan validation layers, RenderDoc capture, Godot export.

## Contracts

- `qa/xodus_studio_contract.py`: exact schema, opt-in only, `core`/`extra` only, valid and unique package names, acyclic profile graph, GPU driver coverage.
- `qa/test_xodus_studio.py`: contract negative cases plus planner determinism, dependency expansion, GPU driver selection, AI tier policy, CLI behaviour, and no subprocess/network use.
- `.github/workflows/xodus-studio-contract.yml`: runs both, then resolves every package with `pacman -Si` in an `archlinux:base` container, weekly and on change.

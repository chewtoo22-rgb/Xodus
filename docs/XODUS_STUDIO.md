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

## Project templates

Starter projects live in [`studio/templates/`](../studio/templates/), one directory per template, declared in [`templates.json`](../studio/templates/templates.json). Each is small original code (under 150 source lines), builds with packages from its Studio profile, and ships a README with build and run commands.

| Template | Studio profile | What it is | Smoke check (from `templates.json`) |
| --- | --- | --- | --- |
| `godot-2d` | engines | Godot 4 scene; a GDScript-driven rectangle moves with arrow keys / gamepad | `godot --headless --path . --import`, then `--check-only --script res://main.gd` |
| `love2d` | engines | LÖVE 11 game with keyboard movement | `luajit -bl` on each `.lua` file (LÖVE runs on LuaJIT) |
| `raylib-c` | engines | raylib game in C99, CMake + Ninja; `find_package(raylib)` with a pkg-config fallback | `cmake -S . -B build -G Ninja && cmake --build build` |
| `sdl3-c` | graphics | SDL3 window, event loop and renderer in C99 (SDL picks Vulkan/GL/software at runtime) | same CMake build |
| `rust-cli-game` | toolchain | Terminal guessing game, Rust standard library only, so it builds offline | `cargo build --offline && cargo test --offline` |

Not yet covered: a raw Vulkan renderer template (the SDL3 template reaches Vulkan only through SDL's renderer) and a Godot 3D template.

```sh
scripts/xodus-studio-new.py --list
scripts/xodus-studio-new.py --template godot-2d --name space-game --dest ~/Projects/space-game
scripts/xodus-studio-new.py --template sdl3-c --name demo --dest ./demo --dry-run
```

The scaffolder copies the template into a new or empty directory and replaces `__XODUS_PROJECT_NAME__` with the project name. It:

- loads templates only through the fail-closed templates contract, so a drifted or tampered template tree is refused;
- accepts names matching lowercase ASCII letters, digits, `_` and `-`, starting with a letter, at most 48 characters, and not a Rust keyword or Cargo build-directory name such as `test`, `fn` or `deps` (so the name is valid for Cargo, CMake and Godot; no path separators, dots, leading dashes or Unicode look-alikes);
- refuses a destination whose final path component is a symlink, a non-empty destination, and one inside the template tree. Parent components of `--dest` are resolved normally. Every directory and file is created relative to one `O_NOFOLLOW` handle on the destination with `O_EXCL`, so a path swapped for a symlink mid-run cannot redirect writes and nothing is overwritten;
- never runs a build or any other program and never uses the network; it prints a JSON summary (files with SHA-256, profiles, install hint, smoke steps) with `executed: false`, and exits `2` on bad input.

Install a template's tools first with the planner, e.g. `scripts/xodus-studio-plan.py --profile engines`.

## Local AI coding assistant

The coding assistant is the Tier 1/Tier 2 local model from [`AI_MODEL_STACK.md`](AI_MODEL_STACK.md), exposed to the editor through the local llama.cpp server (OpenAI-compatible HTTP on localhost). It runs unprivileged, works offline, and never executes code on its own. Suggestions are text the user accepts. When Arena Mode needs the GPU, the model yields like any other local AI workload.

## Roadmap (M7)

1. Manifest, contract, and planner (done).
2. `xodus-studio` desktop app: profile picker, plan preview, confirm, install through the privileged broker, audit-log entry.
3. Project templates: Godot 2D, LÖVE, raylib, SDL3 and Rust templates, scaffolder and Arch CI smoke builds are in place (see above); the CI smoke job still needs a green run. Still open: Godot 3D and a raw Vulkan template.
4. Editor integration for the local assistant (endpoint config, model tier display, offline indicator).
5. "Playtest in Arena": launch the current project in an Arena gamescope session with the overlay on.
6. Hardware validation on the Intel NUC target: Vulkan validation layers, RenderDoc capture, Godot export.

## Contracts

- `qa/xodus_studio_contract.py`: exact schema, opt-in only, `core`/`extra` only, valid and unique package names, acyclic profile graph, GPU driver coverage.
- `qa/test_xodus_studio.py`: contract negative cases plus planner determinism, dependency expansion, GPU driver selection, AI tier policy, CLI behaviour, and no subprocess/network use.
- `qa/xodus_studio_templates_contract.py`: exact schema; template ids match directories; every listed file exists and nothing unlisted, symlinked or non-regular is present; files are UTF-8 text with no NUL/CR; the placeholder appears in exactly the declared files and no unknown `__XODUS_*__` token exists; required profiles exist in the Studio manifest; smoke steps are argv lists (no shell strings, no absolute or `..` arguments) run by listed tools; smoke packages are installed by the template's profiles. `--print-packages` and `--print-ids` feed CI.
- `qa/test_xodus_studio_templates.py`: a negative case for each contract rule, scaffolder happy path for every template, hostile names (`../x`, `/abs`, `-rf`, `.hidden`, fullwidth/zero-width/Cyrillic look-alikes), overwrite and symlink refusal, full placeholder substitution, deterministic output, and no subprocess/network use. `TemplateSmokeBuildTests` scaffolds each template and runs its manifest smoke steps when the toolchain is present, skipping with a reason otherwise; `XODUS_STUDIO_REQUIRE_SMOKE=1` turns a skip into a failure.
- `.github/workflows/xodus-studio-contract.yml`: runs all of the above, resolves every Studio package with `pacman -Si` in an `archlinux:base` container, and in a second `archlinux:base` job installs the template toolchains and runs every smoke build with `XODUS_STUDIO_REQUIRE_SMOKE=1`, weekly and on change.

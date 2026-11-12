---
name: xodus-conventions
description: Conventions for working in the Xodus OS integration repository (Arch/pearOS-based gaming + local-AI desktop). Use when changing qa/ contracts, scripts/ planners, overlay/ boot services, GitHub workflows, or docs in this repo.
---

# Xodus conventions

Xodus is an **integration repository**, not a fork: upstream pearOS sources are pinned in `upstream/*.lock` and Xodus behaviour lives in overlays, scripts, QA contracts and workflows. Read `docs/ARCHITECTURE.md` and `docs/ROADMAP.md` before structural changes.

## Layout and ownership

| Path | Holds |
| --- | --- |
| `overlay/` | Files injected into the ISO before the Arch build (identity, first-boot and live-desktop systemd units/scripts) |
| `scripts/` | Planners and tooling. Planners are **deterministic and non-executing**: they emit a plan (JSON / argv) and never run it (`xodus-arena-session-plan`, `xodus-ai-launch-plan.py`, `xodus-studio-plan.py`) |
| `qa/` | Fail-closed contracts (`*_contract.py`, `*-contract.sh`, `check_*.py`) and their tests (`test_*.py` / `test-*.py`), plus `qa/fixtures/` |
| `studio/`, `labs/` | Workstream manifests (Xodus Studio dev tools, AI Labs) |
| `.github/workflows/` | One workflow per contract, path-filtered to the files it guards |
| `docs/` | Architecture, roadmap, per-workstream specs |

`vendor/`, `build/`, `out/`, `*.iso`, `*.img` are generated and git-ignored.

## Python

- **Standard library only.** No third-party imports; no `pip install` in CI.
- `from __future__ import annotations`, `pathlib.Path`, `ROOT = Path(__file__).resolve().parents[1]`.
- snake_case for functions, variables and module files; PascalCase classes; UPPER_SNAKE constants. Executable scripts in `scripts/` may use kebab-case names; load them in tests with `importlib.util.spec_from_file_location`.
- Tests use **`unittest`** (`python3 -m unittest qa/test_x.py` or `python3 qa/test_x.py`), not pytest. Tests live in `qa/`, not `tests/`.

## Contract style (fail closed)

- Exact key sets: reject missing *and* unexpected keys; reject duplicate JSON keys via `object_pairs_hook`.
- Reject symlinks and non-regular files for evidence/manifest inputs.
- Claims stay `false` until evidence exists (`hardware_validation_claim: false`, `network_required: false`).
- Type-strict checks (`type(x) is int`, so `True` is not accepted as `1`).
- Planners mark `executed: false`, `network_used: false`, and never import `subprocess`/`socket`/`urllib`.
- Each new contract gets negative tests for every rule, not just a happy path.

## Shell

- `set -euo pipefail`; quote every expansion.
- Syntax-check **one script per `bash -n`** call (`for f in …; do bash -n "$f"; done`). `bash -n a b` checks only `a`; `qa/check_shell_syntax_invocations.py` enforces this.

## Workflows

- Every workflow declares top-level `permissions:` (normally `contents: read`); `qa/check_workflow_permissions.py` and `qa/check_workflow_permission_boundary.py` must pass.
- Path-filter `pull_request`/`push` triggers to the files the contract guards.
- Destructive or hardware steps are gated behind explicit qualification and evidence bound to the exact commit SHA; never weaken those gates.

## Commits and PRs

- Subject: `Area: imperative summary`, e.g. `QA: …`, `CI: …`, `AI: …`, `Arena: …`, `Installer: …`, `Studio: …`, `Docs: …`, `M0: …`.
- Body explains why, and states what was verified and what was **not** (no hardware or VM claims without evidence).

## Before pushing

Run the affected contract and its tests, plus:

```sh
for f in qa/test*.py; do python3 "$f" >/dev/null || echo "FAIL $f"; done
python3 qa/check_workflow_permissions.py
python3 qa/check_workflow_permission_boundary.py
python3 qa/check_shell_syntax_invocations.py
```

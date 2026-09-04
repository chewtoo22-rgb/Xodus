# Arena Profile Schema & State-Transition Contract

## Overview

The Arena state planner is a **pure, deterministic function** that models system state transitions for AI runtime power and resource management. It generates:

1. **Enter steps** — ordered transitions to achieve a target Arena profile
2. **Restore steps** — exact reverse-order transitions to restore original state

The planner never executes commands, mutates system state, or downloads content. It produces a JSON plan for downstream services to execute after their own policy checks.

## Schema

### Snapshot (Current System State)

A snapshot captures the current state of four system dimensions:

```json
{
  "schema": 1,
  "power_profile": "balanced",
  "audio_profile": "default",
  "maintenance_paused": false,
  "ai_runtime": "active"
}
```

**Fields:**

| Field | Type | Values | Meaning |
|-------|------|--------|---------|
| `schema` | int | `1` | Contract version (must be 1). |
| `power_profile` | string | `"power-saver"`, `"balanced"`, `"performance"` | System power state. |
| `audio_profile` | string | `"default"`, `"low-latency"` | Audio subsystem mode. |
| `maintenance_paused` | bool | `true`, `false` | Whether background services are suspended. |
| `ai_runtime` | string | `"active"`, `"yielded"` | AI agent state. `"yielded"` means paused for gaming or performance tasks. |

### Request (Desired Arena Profile)

A request specifies the target profile and AI yield intent:

```json
{
  "schema": 1,
  "arena_profile": "performance",
  "yield_ai": true
}
```

**Fields:**

| Field | Type | Values | Meaning |
|-------|------|--------|---------|
| `schema` | int | `1` | Contract version. |
| `arena_profile` | string | `"quiet"`, `"balanced"`, `"performance"` | Target system profile. |
| `yield_ai` | bool | `true`, `false` | Whether to yield the AI runtime (pause it). |

### Plan (Deterministic Transition Steps)

The planner output is an immutable, reversible transition plan:

```json
{
  "schema": 1,
  "arena_profile": "performance",
  "mutates_system": false,
  "hardware_validation_claim": false,
  "enter": [
    {"set": "power_profile", "from": "balanced", "to": "performance"},
    {"set": "audio_profile", "from": "default", "to": "low-latency"},
    {"set": "maintenance_paused", "from": false, "to": true},
    {"set": "ai_runtime", "from": "active", "to": "yielded"}
  ],
  "restore": [
    {"set": "ai_runtime", "from": "yielded", "to": "active"},
    {"set": "maintenance_paused", "from": true, "to": false},
    {"set": "audio_profile", "from": "low-latency", "to": "default"},
    {"set": "power_profile", "from": "performance", "to": "balanced"}
  ]
}
```

**Fields:**

| Field | Type | Meaning |
|-------|------|---------|
| `schema` | int | Contract version. |
| `arena_profile` | string | The requested profile. |
| `mutates_system` | bool | Always `false`. Planner never executes. |
| `hardware_validation_claim` | bool | Always `false`. Planner makes no hardware assertions. |
| `enter` | array | Ordered state transitions to apply. |
| `restore` | array | **Exact reverse order** — transitions to undo enter steps. |

Each step in `enter` and `restore` has:

```json
{"set": "<key>", "from": <value>, "to": <value>}
```

- `set` — the snapshot field to change
- `from` — current value (for validation)
- `to` — target value

## Profile Semantics

### Quiet Profile

Minimizes power consumption for low-performance tasks (web browsing, documents).

| Field | Target |
|-------|--------|
| `power_profile` | `"power-saver"` |
| `audio_profile` | `"default"` |
| `maintenance_paused` | `false` |
| `ai_runtime` | (unchanged) |

### Balanced Profile

Default operational mode. Trades power and latency for responsive interactive use.

| Field | Target |
|-------|--------|
| `power_profile` | `"balanced"` |
| `audio_profile` | `"default"` |
| `maintenance_paused` | `false` |
| `ai_runtime` | (unchanged) |

### Performance Profile

Maximizes responsiveness for gaming and latency-sensitive AI tasks.

| Field | Target |
|-------|--------|
| `power_profile` | `"performance"` |
| `audio_profile` | `"low-latency"` |
| `maintenance_paused` | `true` |
| `ai_runtime` | (controlled by `yield_ai` param) |

- **Suspend background maintenance** to free CPU/IO.
- **Switch to low-latency audio** to reduce jitter (important for rhythm games, VoIP).
- **Power mode unchanged** by AI yield — AI yield is independent of power profile.

## Rollback Guarantees

### Reversibility

Each plan is **strictly reversible**:
- The `restore` array contains exactly the inverse of `enter` steps.
- Applying `restore` steps in order returns the snapshot to its prior state.
- No step can fail if the prior step succeeded (no external state dependencies).

### Idempotence

If the snapshot already matches the target profile, the plan has no `enter` or `restore` steps:

```python
# Snapshot is already "performance"
plan({"power_profile": "performance", ...}, {"arena_profile": "performance"})
# Result:
# "enter": [],
# "restore": []
```

### Double Reversal

Applying enter → restore → enter produces identical enter/restore plans:

```
enter(S) → S' → restore(S') → S → enter(S) → S'  ✓ (cycle)
```

This ensures **partial rollback** is safe: if a step fails midway, applying the full restore sequence will still return to the original state.

## Validation

The planner validates all inputs and **fails closed** on any schema violation:

| Error | Behavior |
|-------|----------|
| Unknown fields in snapshot or request | `ContractError` |
| Missing required fields | `ContractError` |
| Invalid field values | `ContractError` |
| Schema version mismatch | `ContractError` |
| Non-boolean `yield_ai` or `maintenance_paused` | `ContractError` |
| Unsupported profile or power state | `ContractError` |

All validation is **read-only** and deterministic — same inputs always produce the same result.

## Usage

### Command-line

```bash
python3 scripts/arena-state-plan.py <snapshot.json> <request.json>
```

### Python

```python
from arena_state_plan import plan

snapshot = {
    "schema": 1,
    "power_profile": "balanced",
    "audio_profile": "default",
    "maintenance_paused": False,
    "ai_runtime": "active",
}

request = {
    "schema": 1,
    "arena_profile": "performance",
    "yield_ai": True,
}

plan_result = plan(snapshot, request)
print(plan_result["enter"])    # transitions to apply
print(plan_result["restore"])  # how to undo them
```

## Integration Points

The planner is consumed by:

1. **Arena Manager** — Applies `enter` steps, monitors execution, stores plan for recovery.
2. **Recovery Service** — On crash or user request, applies `restore` steps in order.
3. **Hardware Selector** — Reads the plan to validate resource availability before confirming a profile.

## Testing

All state transitions are verified by:

- **`test_restore_plan_reverses_all_enter_transitions`** — Simulates enter → restore and verifies original state is recovered.
- **`test_enter_restore_are_inverse_order`** — Ensures restore steps are exact reverse (not just re-applied in forward order).
- **`test_all_profiles_reversible`** — Tests all combinations of profiles and yield settings.
- **CI contract** — Blocks any modification that introduces mutation primitives or changes `mutates_system` flag.

---

**Last updated:** M0 Arena state-transition planner
**Stability:** Stable
**Changelog:** None (initial release)

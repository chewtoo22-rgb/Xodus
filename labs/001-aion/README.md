# AI Labs 001 — Aion

Status: **Incubator / architecture**

## Mission

Explore an AI-first Xodus interaction layer without replacing or weakening the native Linux desktop. The goal is task-oriented computing: a user expresses an outcome, a planner decomposes it, permissioned agents use bounded tools, and Xodus exposes the result transparently.

This is architectural inspiration, not a Microsoft code or UI clone.

## Workstreams

### 1. AI Shell
- command/conversation surface
- universal contextual search
- task history and resumable sessions
- Spaces-style task workspaces
- native app launching and handoff

### 2. Agent Runtime
- planner
- specialized workers
- bounded tool registry
- explicit capability permissions
- cancellation/timeouts
- audit trail
- failure recovery and rollback hooks

### 3. Local Intelligence
- local model provider abstraction
- hardware-aware model selection
- offline baseline
- optional cloud-provider adapters
- resource budgets for RAM/CPU/GPU

### 4. Xodus Bridge
- applications
- files
- notifications
- safe system information
- settings through allow-listed interfaces
- privileged operations only through explicit authorization boundaries

## Non-goals for the first milestone

- replacing the Xodus desktop
- making AI required for boot/login
- autonomous privileged shell access
- changing the installer or current hardware-validation path
- cloning proprietary Aion implementation details

## Initial architecture

```text
User
  |
AI Shell
  |
Planner
  |
Agent Runtime
  |---- Permission Broker
  |---- Audit Log
  |---- Local Model Provider
  |---- Optional Cloud Providers
  |
Xodus Bridge
  |
Native apps / files / settings / system services
```

## Milestone 0

1. Freeze interfaces between Shell, Runtime, and Bridge.
2. Define capability/permission manifest schema.
3. Define task/event protocol and audit record format.
4. Build a non-privileged mock Bridge.
5. Build one end-to-end demo task against mock tools.
6. Add CI tests proving Labs cannot modify release-critical paths.

## Graduation criteria

A component cannot enter Xodus Core until it has security review, deterministic disable/rollback behavior, offline behavior documented, resource limits, automated tests, and hardware evidence on supported Xodus targets.

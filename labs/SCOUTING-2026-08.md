# Xodus AI Labs — Experimental Project Scouting Map

Date: 2026-08

Purpose: identify external research, experimental operating-system ideas, agent runtimes, local-AI projects, interaction protocols, and security patterns worth reinterpreting for Xodus. This is an idea map, not a commitment to copy upstream products or code.

## Selection rules

A candidate is interesting when it improves at least one of these Xodus goals:

- local-first intelligence
- native Linux integration
- agent safety and auditability
- reversible system changes
- task-oriented user experience
- hardware efficiency
- interoperability with open agent ecosystems
- isolation of experimental features from Xodus Core

## Priority candidates

### Project 002 — Xodus SafeShell
Inspired by NVIDIA OpenShell and capability-based systems such as Genode/Sculpt.

Goal: every autonomous agent runs in a constrained execution envelope instead of receiving ordinary user or root access.

Candidate features:
- declarative filesystem/network/process permissions
- deny-by-default network access
- per-agent sandboxes
- dynamic permission proposals with human approval
- immutable audit records
- kill switch
- temporary credentials
- Landlock/seccomp/bubblewrap or microVM backends

Priority: P0 foundation. Build before powerful agents receive system access.

### Project 003 — Shadow Desktop
Inspired by agent-workspace-linux, computer-use agents, and GUI-agent research.

Goal: give each agent a private virtual desktop so automation never hijacks the user's real mouse, keyboard, clipboard, browser profile, or windows.

Candidate features:
- hidden Wayland/X11 workspace
- disposable browser profile
- floating live viewer
- pause/take-control button
- snapshot/restore
- isolated clipboard
- screen + accessibility observation API

Priority: P0/P1.

### Project 004 — Xodus Dynamic UI
Inspired by A2UI, AG-UI and modern generative-interface research.

Goal: agents return native Xodus interface components instead of dumping everything into chat text.

Candidate features:
- declarative component catalog
- cards, forms, tables, graphs, progress, confirmations
- streamed UI surfaces
- no arbitrary agent-supplied executable UI code
- desktop/mobile/remote rendering compatibility

Priority: P1.

### Project 005 — Xodus Agent Fabric
Inspired by A2A, MCP, AG-UI, Project Solara and emerging Agent OS research.

Goal: vendor-neutral plumbing between users, agents, tools and other agents.

Candidate protocol layers:
- Agent ↔ Tools: MCP-compatible bridge
- Agent ↔ Agent: A2A-compatible bridge
- Agent ↔ User/UI: AG-UI-compatible event layer
- Agent → UI: A2UI-compatible declarative surfaces

Priority: P0/P1 because protocol choices become expensive to change later.

### Project 006 — Local Brain Router
Inspired by Apple on-device models, Ferret-UI Lite, Hugging Face local agents, NVIDIA Nemotron and local-first agent projects.

Goal: automatically select the smallest capable local model for a task and only request cloud escalation when required and permitted.

Candidate features:
- hardware profiler
- RAM/VRAM-aware model selection
- text vs vision vs coding model routing
- quantization-aware profiles
- local-first policy
- explicit cloud escalation prompt
- provider-independent OpenAI-compatible endpoints
- latency/quality/power telemetry

Priority: P1.

### Project 007 — Xodus Spaces
Inspired partly by Project Aion but extended into an OS primitive.

Goal: persistent task workspaces containing the apps, files, browser state, agent memory, terminal sessions and permissions related to one goal.

Candidate features:
- save/resume full task context
- per-space agent memory
- workspace-specific permissions
- snapshots
- share/export space manifest
- automatic cleanup of temporary resources

Priority: P1/P2.

### Project 008 — System Time Machine
Inspired by NixOS atomic generations and COSMIC time-travel debugging concepts.

Goal: make AI-performed system modifications reliably reversible.

Candidate features:
- declarative change plans
- pre-action snapshot
- atomic apply where possible
- configuration generations
- one-click rollback
- boot-menu recovery generation
- explainable change diff

Priority: P0 for any future agent that can alter system configuration.

### Project 009 — Live System Graph
Inspired by Genode Sculpt's live component graph.

Goal: visualize what Xodus and its agents are actually doing.

Candidate features:
- processes/services/agents/tools as nodes
- live relationships and permission edges
- CPU/RAM/GPU/network overlays
- click an agent to inspect task, tools and audit trail
- terminate or isolate directly from graph

Priority: P2, but high UX value.

### Project 010 — Linux Compatibility Capsule
Inspired by Fuchsia Starnix's compatibility-layer philosophy.

Goal: investigate whether selected legacy or risky workloads can run behind a compatibility boundary rather than directly in the host environment.

Near-term interpretation for Xodus should NOT be a new Linux syscall implementation. Instead investigate:
- compatibility containers
- per-app namespaces
- restricted legacy-runtime capsules
- Android runtime integration experiments
- transparent app handoff into isolated environments

Priority: research only / P3.

### Project 011 — Proactive Assistant Lab
Inspired by Apple's PARE research environment.

Goal: determine when an assistant should proactively surface information without becoming an unbearable notification goblin.

Candidate features:
- simulated-user benchmark
- goal inference testing
- intervention timing score
- quiet-mode policy
- confidence thresholds
- reversible suggestions before autonomous action

Priority: P2/P3.

### Project 012 — Multi-Agent Engineering Swarm
Inspired by Google's multi-agent OS-building demonstration and Meta AIRA2.

Goal: a controlled team of agents that can research, design, code, test and critique Labs experiments in parallel.

Candidate roles:
- planner
- implementers
- adversarial reviewer
- security reviewer
- test agent
- benchmark/evaluation agent
- merge coordinator

Required constraints:
- isolated branches/worktrees
- explicit budgets
- bounded runtime
- independent verification
- no direct Core merges

Priority: P1 for accelerating Labs itself.

### Project 013 — Agent Scheduler / AI Control Plane
Inspired by 2026 Agent Operating System research.

Goal: treat long-running agents as governed system workloads rather than chat sessions.

Candidate primitives:
- agent lifecycle
- quotas
- scheduling
- memory/context budgets
- tool capability registry
- trust level
- delegation authority
- confidence
- observability
- checkpoint/restart

Priority: P1/P2.

### Project 014 — Sovereign Memory
Inspired by local-first Agent OS projects such as SOMI and Ghost.

Goal: useful persistent memory that remains user-owned, inspectable and removable.

Candidate features:
- local semantic index
- scoped memory by Space/project
- provenance
- expiry
- edit/delete controls
- sensitive-data boundaries
- memory export/import
- encrypted-at-rest option

Priority: P1.

### Project 015 — Xodus Agent App Store / Skill Registry
Inspired by MCP ecosystems and modular agent platforms.

Goal: install tools/skills without granting them invisible system access.

Candidate features:
- signed skill manifests
- declared capabilities
- reproducible packaging
- version pinning
- reputation/security metadata
- permission preview before install
- sandbox test mode

Priority: P2.

### Project 016 — Personal AI Appliance Mode
Inspired by Project Solara, Perplexity Personal Computer and always-on local-agent systems.

Goal: let Xodus optionally operate as an always-available personal AI node on a mini PC.

Candidate features:
- low-power daemon mode
- remote authenticated control
- voice wake/control option
- secure phone handoff
- scheduled/background agents
- local files/services without exposing full desktop session

Priority: P2.

## Architecture themes worth borrowing

### Genode / Sculpt
Borrow the philosophy of explicit components, capability boundaries, live introspection, safe deployment and user-visible system composition. Do not attempt a kernel rewrite for Xodus.

### Fuchsia / Starnix
Borrow compatibility testing and the idea of first-class compatibility runtimes. Do not rebuild Linux underneath a Linux distribution.

### NixOS
Borrow generations, reproducible configuration and rollback behavior for AI-authored system changes.

### Apple Ferret-UI / on-device models
Borrow the small-model, on-device GUI-agent philosophy and hardware-aware specialization.

### NVIDIA OpenShell / NemoClaw
Borrow default-deny, policy-defined agent execution and observable sandboxes.

### Microsoft Solara / Aion
Borrow dynamic agent loading, task-first shell ideas and device-local agent surfaces, while keeping native Linux apps and local operation first-class.

### Google A2A / A2UI
Borrow protocol interoperability and safe declarative agent-generated interfaces.

### AG-UI
Borrow event-based agent/user state streaming.

### Local-first community Agent OS projects
Borrow provider independence, local file search, user-owned memory, cross-model routing, and modular skills. Avoid blindly inheriting unrestricted shell execution patterns.

## Proposed dependency order

```text
SafeShell + Time Machine + Agent Fabric
                |
                v
       Local Brain Router
                |
                v
       Agent Runtime / Scheduler
          /             \
         v               v
 Shadow Desktop      Sovereign Memory
         \               /
          v             v
            Xodus Spaces
                |
                v
            Dynamic UI
                |
                v
        Proactive Assistant
```

## Implementation waves

### Wave 0 — Guardrails
- Project 002 SafeShell
- Project 005 Agent Fabric contracts
- Project 008 System Time Machine design

### Wave 1 — Intelligence substrate
- Project 006 Local Brain Router
- Project 013 Agent Scheduler
- Project 014 Sovereign Memory

### Wave 2 — Agent interaction
- Project 003 Shadow Desktop
- Project 004 Dynamic UI
- Project 007 Spaces

### Wave 3 — Advanced autonomy
- Project 011 Proactive Assistant
- Project 012 Engineering Swarm
- Project 015 Skill Registry

### Wave 4 — Appliance / experimental system work
- Project 016 Personal AI Appliance Mode
- Project 009 Live System Graph
- Project 010 Compatibility Capsule research

## Critical rule

No experimental project receives unrestricted root access, modifies boot/install/recovery paths, or becomes required for normal Xodus operation until it passes Labs graduation gates.

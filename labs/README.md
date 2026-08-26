# Xodus AI Labs

Xodus AI Labs is the isolated incubator for experimental AI-native capabilities that may eventually graduate into Xodus Core.

## Prime directive

Experiments must not destabilize the production OS, installer, ISO pipeline, or hardware-validation gates.

Xodus Core never depends on unfinished Labs components. Labs integrations consume stable Xodus interfaces and remain optional until promoted.

## Promotion pipeline

`Incubator -> Experiment -> Labs Beta -> Xodus Feature`

Promotion requires documented security boundaries, permission behavior, offline behavior, performance impact, rollback/disable behavior, tests, and hardware validation.

## Projects

- `001-aion/` — AI-first shell and agent-runtime research inspired by Microsoft's Project Aion concepts, rethought for a native, open Xodus environment.

## Rules

1. Native Linux applications remain first-class citizens.
2. Local-first operation is preferred; cloud intelligence is optional.
3. Tool execution is permissioned, auditable, cancellable, and bounded.
4. Experimental features must be independently disableable.
5. No Labs experiment may become a boot, login, installer, or recovery dependency before graduation.
6. Labs work stays isolated from release-critical hardware validation unless explicitly promoted and tested.

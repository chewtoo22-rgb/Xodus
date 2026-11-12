# Xodus Arena

Xodus Arena is the controller-first gaming subsystem built into Xodus while remaining a distinct session, service set, UI, and policy layer. The desktop remains a normal general-purpose Xodus session; Arena Mode switches into a console-like environment optimized for games.

## Product identity

- Product: **Xodus Arena**
- Performance session: **Arena Mode**
- UI: fullscreen, controller-first, mouse/keyboard optional
- Exit path: one controller action returns safely to the Xodus desktop

## Session architecture

Arena Mode should launch as a dedicated Wayland/gamescope session rather than merely maximizing a desktop window. The initial shell can use Steam Gamepad UI while Xodus develops its own launcher/overlay layer.

Primary components:
- gamescope embedded session
- Steam + Proton
- Heroic/Lutris/Bottles integrations for non-Steam libraries
- MangoHud/MangoApp-class telemetry overlay
- PipeWire/WirePlumber audio policy
- GameMode-compatible performance requests
- controller daemon/input mapping
- Xodus Arena Manager for state transitions, profiles, restore, and audit

## Entering Arena Mode

Before launch, Arena Manager records the desktop state and applies a reversible gaming profile:
1. save active power/audio/display/process policy;
2. unload or pause GPU-heavy local AI models when useful;
3. pause nonessential user background applications selected by policy;
4. prevent noncritical scheduled maintenance and package work from starting;
5. switch CPU governor/power profile to the selected gaming profile;
6. apply GPU performance policy where supported;
7. apply display refresh/VRR/HDR profile;
8. apply low-latency audio profile;
9. launch the dedicated gamescope session and controller UI.

Do not blindly kill system services. Every optimization must be allowlisted, reversible, logged, and restored on exit.

## Exiting Arena Mode

Arena Manager restores the saved desktop state, resumes paused applications/services, restores the prior power/audio/display policies, and reloads the local AI runtime if it had yielded resources.

A failed Arena component must fail back to a usable desktop rather than strand the user in a black screen.

## Controller-first requirement

Every primary Arena action must be possible without mouse or keyboard:
- launch/close game
- library navigation and search
- power/sleep/restart
- volume and audio output
- Wi-Fi/Bluetooth/controller pairing
- performance profile
- FPS/telemetry overlay
- screenshots/recording
- scaling/sharpening mode
- return to desktop

On-screen keyboard and controller-driven pointer emulation cover unavoidable text/legacy UI.

## Performance profiles

### Quiet
Lower power/thermal target; useful for indie/emulation/light games.

### Balanced
Default. Good latency and sustained performance without excessive noise/power.

### Performance
Higher CPU/GPU power policy, aggressive background yielding, high-refresh display preference, and local AI unload when it competes for resources.

### Custom
Per-game overrides for resolution, refresh, frame cap, upscaler, HDR, VRR, audio latency, CPU/GPU policy, environment variables, Proton version, and background-app policy.

## Graphics and scaling

Xodus cannot generically "add DLSS" to every game; DLSS requires NVIDIA hardware and game/translation-layer support. Arena should expose supported technologies instead of promising magic injection.

Priority integration:
- NVIDIA DLSS/DLSS Frame Generation when exposed by the game through Proton and supported NVIDIA hardware/driver stack;
- AMD FSR when provided by games or compatible scaling paths;
- Gamescope FSR spatial scaling as a system-level fallback;
- NVIDIA Image Scaling (NIS) through gamescope where available;
- Intel XeSS when supported by the title/Proton stack;
- native resolution and integer/nearest-neighbor scaling for retro titles.

Arena UI should detect GPU vendor, game capabilities, and session support and only show valid options.

## Frame pacing and latency

Per-game controls should include:
- FPS cap
- refresh-rate target
- VRR toggle where supported
- VSync policy
- Gamescope frame limiter
- optional tearing/low-latency policy where supported
- shader pre-caching status
- Proton version selection

The goal is stable frame pacing and low latency, not merely the highest instantaneous FPS counter.

## Audio

Arena audio profiles should support:
- automatic game output selection
- low-latency PipeWire quantum profile when stable
- headset/controller HDMI output switching
- volume normalization optional, off by default
- per-game EQ profiles
- virtual surround/spatial processing only when supported and explicitly enabled
- microphone noise suppression optional

## AI integration

The Xodus assistant remains available through a controller overlay but operates in a resource-aware mode. During demanding games it should prefer a tiny CPU-local model or deterministic tools rather than keeping a large GPU model resident.

Arena assistant capabilities:
- "optimize this game"
- explain graphics options
- select a sensible performance profile
- diagnose Proton launch failures
- change controller layout
- capture telemetry and compare before/after performance
- recommend resolution/upscaling/frame-cap combinations

All changes are previewable, reversible, and stored per game.

## Emulator layer

Arena should treat emulation as a first-class library source. Candidate integrations include RetroArch plus standalone emulators where they offer materially better compatibility. Controller mapping, shaders, bezels, integer scaling, save-state handling, and per-system performance profiles belong behind one Arena UI.

## Validation gates

Before Arena is called ready:
1. controller-only boot -> library -> game -> exit -> desktop loop passes;
2. desktop state restoration passes after normal exit and forced game crash;
3. no critical service is killed by optimization policy;
4. audio device restores correctly;
5. VRR/HDR changes restore correctly;
6. NVIDIA, AMD, and Intel paths fail gracefully when unsupported features are requested;
7. local AI resource yielding/restoration works;
8. per-game profiles are deterministic and reversible.

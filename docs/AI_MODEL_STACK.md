# Xodus AI Model Stack

Xodus is model-agnostic and local-first. The operating system presents one Xodus assistant and routes work to the best available model according to capability, latency, privacy policy, hardware, and user preference.

## Runtime tiers

### Tier 0: deterministic system tools
Use typed system APIs and deterministic helpers instead of an LLM when a task does not require reasoning. Examples: volume, display, process control, package status, hardware telemetry, file metadata, launching applications, and Arena Mode transitions.

### Tier 1: fast local assistant
Target small 3B-8B instruct models that can run acceptably on CPU/iGPU systems. Initial supported families should include:
- Qwen 3 small instruct variants
- Llama 3.2 / newer small instruct variants where licensing permits redistribution or user-side download
- Gemma 3 small variants where licensing permits
- Phi small instruct variants

Use cases: system Q&A, settings help, command classification, local search summaries, tutorial assistance, simple automation planning, and offline operation.

### Tier 2: strong local model
On systems with sufficient RAM/VRAM, allow 8B-14B+ quantized models through llama.cpp/Ollama-compatible runtimes. Candidate families include Qwen, Llama, Gemma, Mistral, and other user-installed GGUF-compatible models.

Use cases: coding, multi-step planning, document work, richer local reasoning, and AI Labs experiments.

### Tier 3: optional cloud escalation
Cloud providers are optional connectors, never a boot/runtime dependency. They may be used for hard reasoning, large-context work, vision, image generation, or coding when the user enables them. Xodus must remain functional with every cloud connector disabled.

## Router policy

The Xodus AI Router selects a backend using:
1. explicit user model pinning;
2. privacy policy / offline mode;
3. task capability requirements;
4. available RAM/VRAM and thermal/power budget;
5. latency target;
6. fallback availability.

System actions remain behind explicit typed permissions and an audit trail regardless of which model produced the plan.

## Hardware profiles

### NUC / CPU-first
Default to a 3B-4B quantized local assistant. Offer a 7B-8B option when RAM headroom permits. The model runtime must yield resources when Xodus Arena enters a high-performance gaming profile.

### Gaming desktop / discrete GPU
Allow larger quantized local models when VRAM headroom is available. Arena Mode may pause or unload GPU-resident models before launching games and restore them on exit.

## Runtime compatibility

Primary local runtime target: llama.cpp-compatible GGUF execution, with an adapter for Ollama-style model management where useful. This keeps Xodus independent of one vendor and lets users bring their own local models.

## Privacy contract

- Local is the default path for system-sensitive data.
- Cloud use is opt-in and visible.
- Every system action is permission-gated and auditable.
- Model downloads and licenses are tracked independently from Xodus source licensing.
- AI Labs experiments cannot silently become production defaults.

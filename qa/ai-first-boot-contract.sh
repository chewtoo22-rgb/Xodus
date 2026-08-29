#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
runner="$repo_root/overlay/first-boot/xodus-ai-first-boot"
unit="$repo_root/overlay/first-boot/xodus-ai-first-boot.service"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

make_selector() {
  local path=$1 payload=$2
  cat > "$path" <<EOF
#!/usr/bin/env bash
printf '%s\n' '$payload'
EOF
  chmod +x "$path"
}

root="$tmp/root"
mkdir -p "$root/var/lib/xodus/first-boot"
printf 'schema=1\n' > "$root/var/lib/xodus/first-boot/complete"
selector="$tmp/selector"
make_selector "$selector" '{"hardware":{"cpu_threads":8,"gpu_vendor":"intel","ram_gib":31.2,"vram_gib":0.0},"recommendation":{"backend":"vulkan","max_model_class":"3B-4B","preferred_quant":"Q4_K_M","reason":"test","tier":"standard"}}'
XODUS_AI_FIRST_BOOT_ROOT="$root" XODUS_AI_SELECTOR="$selector" bash "$runner"
selection="$root/var/lib/xodus/ai/hardware-selection.json"
test -s "$selection"
python3 - "$selection" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p["recommendation"]["tier"] == "standard"
assert p["recommendation"]["backend"] == "vulkan"
assert p["hardware"]["cpu_threads"] == 8
PY

before=$(sha256sum "$selection" | awk '{print $1}')
make_selector "$selector" '{"hardware":{"cpu_threads":1,"gpu_vendor":"none","ram_gib":8,"vram_gib":0},"recommendation":{"backend":"cpu","max_model_class":"1B-3B","preferred_quant":"Q4_K_M","reason":"changed","tier":"lite"}}'
XODUS_AI_FIRST_BOOT_ROOT="$root" XODUS_AI_SELECTOR="$selector" bash "$runner"
after=$(sha256sum "$selection" | awk '{print $1}')
test "$before" = "$after"

pending="$tmp/pending"
mkdir -p "$pending"
XODUS_AI_FIRST_BOOT_ROOT="$pending" XODUS_AI_SELECTOR="$selector" bash "$runner"
test ! -e "$pending/var/lib/xodus/ai/hardware-selection.json"

bad="$tmp/bad"
mkdir -p "$bad/var/lib/xodus/first-boot"
printf 'schema=1\n' > "$bad/var/lib/xodus/first-boot/complete"
make_selector "$selector" '{"hardware":{},"recommendation":{"tier":"surprise"}}'
if XODUS_AI_FIRST_BOOT_ROOT="$bad" XODUS_AI_SELECTOR="$selector" bash "$runner"; then
  echo 'expected malformed selector output to fail closed' >&2
  exit 1
fi
test ! -e "$bad/var/lib/xodus/ai/hardware-selection.json"

grep -Fxq 'After=xodus-first-boot.service' "$unit"
grep -Fxq 'ConditionPathExists=/var/lib/xodus/first-boot/complete' "$unit"
grep -Fxq 'ConditionPathExists=/usr/lib/xodus/xodus-ai-select.py' "$unit"
grep -Fxq 'ConditionPathExists=!/var/lib/xodus/ai/hardware-selection.json' "$unit"
grep -Fxq 'ReadWritePaths=/var/lib/xodus/ai' "$unit"

# This stage may inspect hardware and write local state only. Model retrieval or
# remote escalation belongs behind separately-reviewed catalog/artifact gates.
if grep -Eqi '\b(curl|wget|git clone|pip install|npm install)\b|https?://' "$runner"; then
  echo 'AI first-boot runner contains a network/download primitive' >&2
  exit 1
fi

echo 'AI first-boot contract: PASS'

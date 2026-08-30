#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
patcher="$repo_root/scripts/patch-installer-xodus-payload.py"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/setup" <<'EOF'
#!/bin/bash
error_exit() { exit 1; }
  # Sends the install finished messages to the frontend
  echo "Installation finished"
EOF
python3 "$patcher" "$tmp/setup" "$tmp/patched" > "$tmp/report"
python3 -m py_compile "$patcher"
bash -n "$tmp/patched"
grep -Fqx 'xodus_payload_handoff=first-boot-ai-first-boot-fail-closed' "$tmp/report"
grep -Fq '/usr/lib/xodus/xodus-first-boot' "$tmp/patched"
grep -Fq '/usr/lib/systemd/system/xodus-first-boot.service' "$tmp/patched"
grep -Fq '/usr/lib/xodus/xodus-ai-first-boot' "$tmp/patched"
grep -Fq 'Installed image unexpectedly pre-marked first boot complete' "$tmp/patched"
grep -Fq 'multi-user.target.wants/xodus-first-boot.service' "$tmp/patched"
# Refuse silent adaptation if the audited upstream completion boundary changes.
sed 's/Sends the install finished/Sends install finished/' "$tmp/setup" > "$tmp/drifted"
if python3 "$patcher" "$tmp/drifted" "$tmp/should-not-exist" >/dev/null 2>&1; then
  echo 'expected installer contract drift to fail closed' >&2
  exit 1
fi
echo 'installer Xodus payload contract: PASS'

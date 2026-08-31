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
grep -Fqx 'xodus_payload_handoff=embedded-qualified-bytes-first-boot-ai-first-boot-build-provenance-fail-closed' "$tmp/report"
grep -Eq '^xodus_source_commit=[0-9a-f]{40}$' "$tmp/report"
grep -Eq '^xodus_upstream_commit=[0-9a-f]{40}$' "$tmp/report"
grep -Fq 'xodus_payload=/usr/lib/xodus/xodus-first-boot:0755:' "$tmp/report"
grep -Fq 'xodus_payload=/usr/lib/systemd/system/xodus-first-boot.service:0644:' "$tmp/report"
grep -Fq 'xodus_payload=/usr/lib/xodus/xodus-ai-first-boot:0755:' "$tmp/report"
grep -Fq 'xodus_payload=/usr/lib/systemd/system/xodus-ai-first-boot.service:0644:' "$tmp/report"
grep -Fq 'xodus_payload=/usr/lib/xodus/xodus-ai-select.py:0755:' "$tmp/report"
grep -Fq 'xodus_payload=/usr/lib/xodus/build-info:0644:' "$tmp/report"
grep -Fq 'Do not depend on the booted live ISO already containing these files.' "$tmp/patched"
grep -Fq 'sha256sum -c -' "$tmp/patched"
grep -Fq '/mnt/usr/lib/xodus/xodus-first-boot' "$tmp/patched"
grep -Fq '/mnt/usr/lib/xodus/xodus-ai-first-boot' "$tmp/patched"
grep -Fq '/mnt/usr/lib/xodus/xodus-ai-select.py' "$tmp/patched"
grep -Fq '/mnt/usr/lib/xodus/build-info' "$tmp/patched"
grep -Fq 'Installed Xodus source provenance verification failed' "$tmp/patched"
grep -Fq 'Installed Xodus upstream provenance verification failed' "$tmp/patched"
grep -Fq 'Installed image unexpectedly pre-marked first boot complete' "$tmp/patched"
grep -Fq 'multi-user.target.wants/xodus-first-boot.service' "$tmp/patched"
grep -Fq 'multi-user.target.wants/xodus-ai-first-boot.service' "$tmp/patched"
# The generated installer must be self-contained: delete the qualification
# source payloads after generation and prove the generated shell still parses.
cp "$tmp/patched" "$tmp/self-contained"
bash -n "$tmp/self-contained"
# Refuse silent adaptation if the audited upstream completion boundary changes.
sed 's/Sends the install finished/Sends install finished/' "$tmp/setup" > "$tmp/drifted"
if python3 "$patcher" "$tmp/drifted" "$tmp/should-not-exist" >/dev/null 2>&1; then
  echo 'expected installer contract drift to fail closed' >&2
  exit 1
fi
echo 'installer Xodus embedded payload contract: PASS'

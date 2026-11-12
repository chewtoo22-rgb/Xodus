#!/usr/bin/env bash
set -euo pipefail

unit="overlay/first-boot/xodus-ai-runtime-preflight.service"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$unit" ]] || fail "missing $unit"

require_line() {
  local expected="$1"
  grep -Fqx "$expected" "$unit" || fail "missing required directive: $expected"
}

require_line "After=xodus-ai-first-boot.service"
require_line "Requires=xodus-ai-first-boot.service"
require_line "ConditionPathExists=/var/lib/xodus/ai/hardware-selection.json"
require_line "ExecStart=/usr/bin/python3 /usr/lib/xodus/xodus-ai-runtime-preflight.py --output /var/lib/xodus/ai/runtime-readiness.json"
require_line "NoNewPrivileges=yes"
require_line "PrivateTmp=yes"
require_line "PrivateDevices=yes"
require_line "ProtectSystem=strict"
require_line "ProtectHome=yes"
require_line "ProtectKernelTunables=yes"
require_line "ProtectKernelModules=yes"
require_line "ProtectControlGroups=yes"
require_line "RestrictSUIDSGID=yes"
require_line "RestrictNamespaces=yes"
require_line "LockPersonality=yes"
require_line "SystemCallArchitectures=native"
require_line "ReadWritePaths=/var/lib/xodus/ai"
require_line "WantedBy=multi-user.target"

if grep -Eq '(^|[[:space:]])(curl|wget|nc|ncat|socat)([[:space:]]|$)' "$unit"; then
  fail "network/download primitive present in runtime preflight unit"
fi

if grep -Eq 'ExecStart=.*(sh -c|bash -c)' "$unit"; then
  fail "runtime preflight must not execute through a shell"
fi

if grep -Eq '^ReadWritePaths=.*(/etc|/usr|/boot|/efi|/home|/root)' "$unit"; then
  fail "runtime preflight writable surface escaped /var/lib/xodus/ai"
fi

echo "PASS: local AI runtime preflight service contract"

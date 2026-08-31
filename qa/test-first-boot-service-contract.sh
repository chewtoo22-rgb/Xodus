#!/usr/bin/env bash
set -euo pipefail

unit="overlay/first-boot/xodus-first-boot.service"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$unit" ]] || fail "missing $unit"

require_line() {
  local expected="$1"
  grep -Fqx "$expected" "$unit" || fail "missing required directive: $expected"
}

require_line "After=local-fs.target systemd-machine-id-commit.service"
require_line "Before=graphical.target"
require_line "ConditionPathExists=!/var/lib/xodus/first-boot/complete"
require_line "ExecStart=/usr/lib/xodus/xodus-first-boot"
require_line "NoNewPrivileges=yes"
require_line "PrivateTmp=yes"
require_line "PrivateDevices=yes"
require_line "ProtectHome=yes"
require_line "ProtectSystem=strict"
require_line "ProtectKernelTunables=yes"
require_line "ProtectKernelModules=yes"
require_line "ProtectControlGroups=yes"
require_line "RestrictSUIDSGID=yes"
require_line "RestrictNamespaces=yes"
require_line "LockPersonality=yes"
require_line "SystemCallArchitectures=native"
require_line "ReadWritePaths=/var/lib/xodus/first-boot"
require_line "WantedBy=multi-user.target"

if grep -Eq 'ExecStart=.*(sh -c|bash -c)' "$unit"; then
  fail "first-boot service must not execute through a shell"
fi

if grep -Eq '^ReadWritePaths=.*(/etc|/usr|/boot|/efi|/home|/root)' "$unit"; then
  fail "first-boot writable surface escaped /var/lib/xodus/first-boot"
fi

if grep -Eq '^Exec(Start|StartPre|StartPost)=.*(^|[[:space:]])(curl|wget|nc|ncat|socat)([[:space:]]|$)' "$unit"; then
  fail "network/download primitive present in first-boot unit"
fi

if grep -Eq '^CapabilityBoundingSet=.*(CAP_SYS_ADMIN|CAP_SYS_MODULE|CAP_SYS_RAWIO)' "$unit"; then
  fail "unsafe broad capability granted to first-boot service"
fi

echo "PASS: first-boot foundation service contract"

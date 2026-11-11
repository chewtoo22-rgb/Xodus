#!/usr/bin/env bash
set -euo pipefail

ISO_PATH="${1:-}"
OUTDIR="${2:-destructive-qualified-evidence}"
EXPECTED_SHA="${XODUS_CANDIDATE_SHA:-}"

if [[ -z "$ISO_PATH" || ! -f "$ISO_PATH" ]]; then
  echo "usage: $0 <iso-path> [output-dir]" >&2
  exit 64
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gate="$repo_root/qa/installer-vm-destructive.sh"
[[ -x "$gate" || -f "$gate" ]] || { echo "ERROR: destructive gate missing" >&2; exit 66; }
command -v git >/dev/null || { echo "ERROR: git missing" >&2; exit 69; }
command -v sha256sum >/dev/null || { echo "ERROR: sha256sum missing" >&2; exit 69; }

if [[ -z "$EXPECTED_SHA" ]]; then
  EXPECTED_SHA="$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || true)"
fi
if [[ ! "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: candidate SHA must be an exact 40-character lowercase commit SHA" >&2
  exit 65
fi

# A qualification run must describe code that actually exists in this checkout.
# This prevents evidence from being labeled with an unrelated or mistyped SHA.
if ! git -C "$repo_root" cat-file -e "${EXPECTED_SHA}^{commit}" 2>/dev/null; then
  echo "ERROR: candidate SHA is not present in this checkout" >&2
  exit 65
fi

mkdir -p "$OUTDIR"
OUTDIR="$(readlink -f "$OUTDIR")"
ISO_PATH="$(readlink -f "$ISO_PATH")"
ISO_SHA256="$(sha256sum "$ISO_PATH" | awk '{print $1}')"
[[ "$ISO_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "ERROR: failed to hash candidate ISO" >&2; exit 1; }

cat >"$OUTDIR/candidate-provenance.txt" <<EOF
candidate_sha=$EXPECTED_SHA
iso_path=$ISO_PATH
iso_sha256=$ISO_SHA256
qualification_gate=qa/installer-vm-destructive.sh
provenance_complete=yes
EOF

# Run the existing destructive VM gate unchanged. Its disposable-target guard,
# audited installer driver and post-install UEFI smoke remain the authority.
bash "$gate" "$ISO_PATH" "$OUTDIR/destructive"

grep -Fxq 'destructive_vm_install_gate=pass' "$OUTDIR/destructive/destructive-gate-summary.txt"
grep -Fxq 'post_install_uefi_userspace=pass' "$OUTDIR/destructive/destructive-gate-summary.txt"

{
  echo "x1_candidate_qualification=pass"
  echo "candidate_sha=$EXPECTED_SHA"
  echo "iso_sha256=$ISO_SHA256"
  echo "destructive_vm_install_gate=pass"
  echo "post_install_uefi_userspace=pass"
  echo "physical_hardware_validation=not_claimed"
} | tee "$OUTDIR/qualification-summary.txt"

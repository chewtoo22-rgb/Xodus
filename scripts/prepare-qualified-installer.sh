#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
lock="${1:-$repo_root/upstream/installer.lock}"
outdir="${2:-qualified-installer}"

audit="$repo_root/scripts/audit-installer-driver.sh"
patcher="$repo_root/scripts/patch-installer-xodus-payload.py"
for dep in "$lock" "$audit" "$patcher"; do
  [[ -f "$dep" ]] || { echo "ERROR: required installer preparation dependency missing: $dep" >&2; exit 66; }
done

# Qualified installer output is release evidence. Never reuse or recursively
# clean an existing destination: that could destroy prior qualification data
# or redirect writes through a symlink. Require a real, existing parent and a
# brand-new output directory instead.
out_parent="$(dirname -- "$outdir")"
out_name="$(basename -- "$outdir")"
[[ -n "$out_name" && "$out_name" != "." && "$out_name" != ".." ]] || {
  echo "ERROR: invalid qualified installer output path: $outdir" >&2
  exit 73
}
[[ -d "$out_parent" ]] || {
  echo "ERROR: qualified installer output parent does not exist: $out_parent" >&2
  exit 73
}
parent_abs="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$out_parent")"
parent_real="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$out_parent")"
[[ "$parent_abs" == "$parent_real" ]] || {
  echo "ERROR: qualified installer output parent traverses a symlink: $out_parent" >&2
  exit 73
}
if [[ -e "$outdir" || -L "$outdir" ]]; then
  echo "ERROR: qualified installer output already exists; refusing to overwrite evidence: $outdir" >&2
  exit 73
fi
mkdir -- "$outdir"
outdir="$(cd "$outdir" && pwd -P)"
audit_dir="$outdir/audit"
mkdir -- "$audit_dir"

bash "$audit" "$lock" "$audit_dir" | tee "$outdir/audit-report.txt"
# installer.lock is repository-controlled data and is sourced only after the
# audit step has validated the pinned upstream contract.
# shellcheck disable=SC1090
source "$lock"
: "${SETUP_PATH:?audited installer lock did not define SETUP_PATH}"
setup="$audit_dir/$SETUP_PATH"
[[ -s "$setup" ]] || { echo "ERROR: audited installer setup missing: $setup" >&2; exit 1; }

prepared="$outdir/setup.xodus-qualified"
python3 "$patcher" "$setup" "$prepared" | tee "$outdir/payload-handoff-report.txt"
[[ -s "$prepared" && -x "$prepared" ]] || { echo "ERROR: prepared installer is not executable" >&2; exit 1; }

grep -Fq '/usr/lib/xodus/xodus-first-boot' "$prepared" || { echo "ERROR: first-boot payload handoff absent" >&2; exit 1; }
grep -Fq 'multi-user.target.wants/xodus-first-boot.service' "$prepared" || { echo "ERROR: first-boot enablement absent" >&2; exit 1; }
grep -Fq '/usr/lib/xodus/xodus-ai-first-boot' "$prepared" || { echo "ERROR: AI first-boot payload handoff absent" >&2; exit 1; }

sha256sum "$setup" "$prepared" | tee "$outdir/installer.sha256"
printf 'qualified_installer=%s\n' "$prepared"
printf 'qualification=audited-upstream-plus-xodus-payload-handoff\n'

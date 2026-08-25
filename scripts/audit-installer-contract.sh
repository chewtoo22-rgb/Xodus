#!/usr/bin/env bash
set -euo pipefail

lock_file="${1:-upstream/installer.lock}"
source "$lock_file"

: "${REPO:?missing REPO}"
: "${REF:?missing REF}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git clone --quiet --no-checkout "$REPO" "$work/installer"
git -C "$work/installer" fetch --quiet --depth=1 origin "$REF"
git -C "$work/installer" checkout --quiet --detach FETCH_HEAD

actual="$(git -C "$work/installer" rev-parse HEAD)"
[[ "$actual" == "$REF" ]] || { echo "installer pin mismatch: $actual != $REF" >&2; exit 1; }

setup="$work/installer/system_install/setup"
readme="$work/installer/README.md"
[[ -f "$setup" && -f "$readme" ]] || { echo "expected installer files missing" >&2; exit 1; }

# The current upstream installer is intentionally destructive. Until the
# expendable-VM install gate exists, Xodus treats any semantic drift here as a
# review event instead of silently inheriting changed disk behavior.
grep -Fq 'wipefs -a "$DISK"' "$setup"
grep -Fq 'parted -s "$DISK" mklabel gpt' "$setup"
grep -Fq 'mkfs."$FILE_SYSTEM" "$ROOT_PART"' "$setup"
grep -Fqi 'WHOLE' "$readme"
grep -Fqi 'erased' "$readme"

# Guard against accidental hard-coded physical targets in our pinned script.
if grep -Eq '(^|[[:space:]])/dev/(sda|nvme0n1)([[:space:]]|$)' "$setup"; then
  echo "hard-coded physical disk path found in upstream installer" >&2
  exit 1
fi

echo "Installer contract audit passed for $REF"
echo "Policy: ${POLICY:-unspecified}"

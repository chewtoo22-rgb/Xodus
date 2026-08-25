#!/usr/bin/env bash
set -euo pipefail

lock_file="${1:-upstream/installer.lock}"
workdir="${2:-${RUNNER_TEMP:-/tmp}/xodus-installer-audit}"

[[ -f "$lock_file" ]] || { echo "missing installer lock: $lock_file" >&2; exit 2; }

# shellcheck disable=SC1090
source "$lock_file"
: "${REPO:?missing REPO}"
: "${REF:?missing REF}"
: "${SETUP_PATH:?missing SETUP_PATH}"
: "${SETUP_BLOB:?missing SETUP_BLOB}"

[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "REF must be a full commit SHA" >&2; exit 3; }
[[ "$SETUP_BLOB" =~ ^[0-9a-f]{40}$ ]] || { echo "SETUP_BLOB must be a full git blob SHA" >&2; exit 4; }

rm -rf "$workdir"
git clone --filter=blob:none --no-checkout "$REPO" "$workdir" >/dev/null 2>&1
git -C "$workdir" checkout --detach "$REF" >/dev/null 2>&1

actual_blob="$(git -C "$workdir" rev-parse "HEAD:$SETUP_PATH")"
[[ "$actual_blob" == "$SETUP_BLOB" ]] || {
  echo "installer setup blob drift: expected $SETUP_BLOB got $actual_blob" >&2
  exit 5
}

setup="$workdir/$SETUP_PATH"
[[ -s "$setup" ]] || { echo "missing pinned setup entrypoint: $setup" >&2; exit 6; }
bash -n "$setup"

require_literal() {
  local needle="$1"
  grep -Fq -- "$needle" "$setup" || {
    echo "installer contract drift: missing literal: $needle" >&2
    exit 10
  }
}

# Deterministic target contract: the whole-disk target comes only from argv[1]
# before destructive partitioning begins.
require_literal 'DISK="$1"'
require_literal 'wipefs -a "$DISK"'
require_literal 'parted -s "$DISK" mklabel gpt'
require_literal 'sgdisk -n 1:0:+512M -n 2:0:0 -t 1:ef00 -t 2:8300 "$DISK"'
require_literal 'partprobe "$DISK"'

# The test driver relies on the install being rooted at /mnt and on the script
# surfacing progress through /tmp/progress. If either changes, automation must
# stop and be reviewed rather than guessing.
require_literal 'mount "$ROOT_PART" /mnt'
require_literal '> /tmp/progress'

first_disk_line="$(grep -nF 'DISK="$1"' "$setup" | head -n1 | cut -d: -f1)"
first_wipe_line="$(grep -nF 'wipefs -a "$DISK"' "$setup" | head -n1 | cut -d: -f1)"
[[ -n "$first_disk_line" && -n "$first_wipe_line" && "$first_disk_line" -lt "$first_wipe_line" ]] || {
  echo "installer contract drift: target assignment no longer precedes destructive wipe" >&2
  exit 11
}

cat <<EOF
INSTALLER DRIVER CONTRACT PASS
repo=$REPO
ref=$REF
setup_path=$SETUP_PATH
setup_blob=$actual_blob
target_source=argv1
destructive_boundary=wipefs
install_root=/mnt
physical_policy=${POLICY:-unknown}
EOF

#!/usr/bin/env bash
set -euo pipefail

# Run in the Arch build container after packages/customize_airootfs and before
# the final live-root identity assertions and squashfs generation.
profile=${1:-}
live_root=${2:-}
[[ -n "$profile" && -d "$profile/airootfs" && -n "$live_root" &&
   -d "$live_root" && "$live_root" != / && ! -L "$live_root" ]] || {
  echo 'usage: build-settings.sh <pear-profile-dir> <live-root>' >&2
  exit 64
}
overlay="$profile/xodus-settings"
[[ -d "$overlay" && ! -L "$overlay" ]] || exit 65
for source in source.lock.json release-source.lock.json upstream-os-release prepare-source.py apply-settings.py; do
  [[ -f "$overlay/$source" && ! -L "$overlay/$source" ]] || exit 65
done
command -v git >/dev/null
command -v cmake >/dev/null
command -v ninja >/dev/null

# Lock values are parsed as data and are never sourced as shell code.
mapfile -t lock < <(python3 - "$overlay/source.lock.json" <<'PY'
import json, re, sys
data = json.load(open(sys.argv[1]))
assert data['repository'] == 'https://github.com/pearOS-archlinux/pkgbuilds.git'
assert re.fullmatch('[0-9a-f]{40}', data['commit'])
print(data['repository'])
print(data['commit'])
PY
)
[[ ${#lock[@]} -eq 2 ]] || exit 65
scratch=$(mktemp -d /var/tmp/xodus-settings-build.XXXXXXXX)
# The container lifecycle cleans the compile source; retain this path on failure
# so build diagnostics can identify the exact prepared inputs.
git init -q "$scratch/vendor"
git -C "$scratch/vendor" remote add origin "${lock[0]}"
git -C "$scratch/vendor" fetch --depth 1 origin "${lock[1]}"
git -C "$scratch/vendor" checkout -q --detach FETCH_HEAD
python3 "$overlay/prepare-source.py" "$scratch/vendor" "$scratch/source"
cmake -G Ninja -S "$scratch/source" -B "$scratch/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$scratch/build" --parallel "${XODUS_BUILD_JOBS:-4}"
binary="$scratch/build/systemsettings1"
[[ -s "$binary" && -x "$binary" && ! -L "$binary" ]] || exit 70
[[ "$(od -An -tx1 -N4 "$binary" | tr -d ' \n')" == 7f454c46 ]] || exit 70
python3 "$overlay/apply-settings.py" "$live_root" "$binary" "$scratch/source/license.txt"

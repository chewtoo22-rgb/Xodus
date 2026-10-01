#!/usr/bin/env bash
set -euo pipefail

# Runs inside the same Arch container that builds the live filesystem. The
# resulting binary is checked against the installed Qt libraries and for
# execute mode in the staged live root before the squashfs is constructed.
profile=${1:-}
live_root=${2:-}
[[ -n "$profile" && -d "$profile/airootfs" && -n "$live_root" &&
   -d "$live_root" && "$live_root" != / && ! -L "$live_root" ]] || {
  echo 'usage: build-welcome.sh <pear-profile-dir> <live-root>' >&2
  exit 64
}
source="$profile/xodus-welcome.cpp"
output="$live_root/usr/lib/xodus/xodus-welcome"
test -f "$source" && test ! -L "$source"
test ! -e "$output" && test ! -L "$output"
command -v c++ >/dev/null
command -v pkg-config >/dev/null
pkg-config --atleast-version=5.15 Qt5Widgets

install -d "$(dirname "$output")"
c++ -std=c++17 -O2 -fPIC -pie -Wall -Wextra \
  "$source" -o "$output" $(pkg-config --cflags --libs Qt5Widgets)
chmod 0755 "$output"
test -s "$output" && test -x "$output"
test "$(od -An -tx1 -N4 "$output" | tr -d ' \n')" = 7f454c46

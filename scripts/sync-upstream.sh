#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT_DIR/upstream/pearos-repos.txt"
VENDOR_DIR="$ROOT_DIR/vendor"
LOCKFILE="$ROOT_DIR/upstream/pearos-lock.txt"

mkdir -p "$VENDOR_DIR"
: > "$LOCKFILE"

while IFS='|' read -r name url branch; do
  [[ -z "${name:-}" || "$name" == \#* ]] && continue
  target="$VENDOR_DIR/$name"

  if [[ -d "$target/.git" ]]; then
    git -C "$target" fetch --depth=1 origin "$branch"
    git -C "$target" checkout -q "$branch"
    git -C "$target" reset --hard "origin/$branch"
  else
    git clone --depth=1 --branch "$branch" "$url" "$target"
  fi

  sha="$(git -C "$target" rev-parse HEAD)"
  printf '%s|%s|%s|%s\n' "$name" "$url" "$branch" "$sha" >> "$LOCKFILE"
done < "$MANIFEST"

printf 'Wrote %s\n' "$LOCKFILE"

#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
fetch="$repo_root/scripts/fetch-qualified-candidate.sh"
writer="$repo_root/scripts/write-candidate-usb.sh"
bash -n "$fetch" "$writer"
command -v jq >/dev/null 2>&1 || { echo 'jq is required for this contract' >&2; exit 2; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
sha=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
upstream_sha=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
iso_name=Xodus-reference-fixture.iso
export FIXTURE_DIR="$tmp/remote"
mkdir -p "$FIXTURE_DIR" "$tmp/bin"

make_core() {
  local destination="$1" layout="$2" iso_dir digest
  iso_dir="$destination/$layout"
  mkdir -p "$iso_dir"
  printf 'Xodus ISO fixture bytes\n' > "$iso_dir/$iso_name"
  digest="$(sha256sum "$iso_dir/$iso_name")"
  digest="${digest%% *}"
  printf '%s  pearos-iso/%s\n' "$digest" "$iso_name" > "$iso_dir/xodus-reference.sha256"
  cat > "$iso_dir/xodus-reference.manifest" <<EOF
schema=1
xodus_source_commit=$sha
upstream_commit=$upstream_sha
iso_filename=$iso_name
iso_sha256=$digest
EOF
}

make_manifest() {
  local destination="$1"
  jq -n --arg sha "$sha" --arg artifact "xodus-reference-iso-$upstream_sha" '
    {schema: 1, candidate_sha: $sha,
     policy: "live-boot-only",
     core_iso: {run_id: 200, artifact_id: 500, artifact_name: $artifact},
     qa_qemu: {run_id: 201}}
  ' > "$destination"
}

make_core "$FIXTURE_DIR/core" ''
mkdir -p "$FIXTURE_DIR/qualification"
make_manifest "$FIXTURE_DIR/qualification/hardware-candidate.json"
cat > "$FIXTURE_DIR/runs.json" <<EOF
{"workflow_runs":[{"id":300,"head_sha":"$sha","head_branch":"main","status":"completed","conclusion":"success"}]}
EOF
cat > "$FIXTURE_DIR/main.json" <<EOF
{"commit":{"sha":"$sha"}}
EOF
cat > "$FIXTURE_DIR/core-run.json" <<EOF
{"head_sha":"$sha","status":"completed","conclusion":"success"}
EOF
cat > "$FIXTURE_DIR/qa-run.json" <<EOF
{"head_sha":"$sha","status":"completed","conclusion":"success"}
EOF

# Local GitHub CLI stand-in: no network, credentials, or real artifact download.
cat > "$tmp/bin/gh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == api ]]; then
  case "$2" in
    */actions/workflows/hardware-candidate.yml/runs\?*) source="$FIXTURE_DIR/runs.json" ;;
    */branches/main) source="$FIXTURE_DIR/main.json" ;;
    */actions/runs/200) source="$FIXTURE_DIR/core-run.json" ;;
    */actions/runs/201) source="$FIXTURE_DIR/qa-run.json" ;;
    *) echo "unexpected gh api path: $2" >&2; exit 90 ;;
  esac
  if [[ "${3:-}" == --jq ]]; then
    jq -r "$4" "$source"
  else
    cat "$source"
  fi
  exit 0
fi
[[ "${1:-}" == run && "${2:-}" == download ]] || exit 91
run_id="$3"
shift 3
name=''
destination=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) shift 2 ;;
    --name) name="$2"; shift 2 ;;
    --dir) destination="$2"; shift 2 ;;
    *) echo "unexpected gh run option: $1" >&2; exit 92 ;;
  esac
done
[[ -n "$name" && -n "$destination" ]] || exit 93
mkdir -p "$destination"
case "$run_id" in
  300) [[ "$name" == hardware-candidate-* ]] || exit 94
       cp -a "$FIXTURE_DIR/qualification/." "$destination/" ;;
  200) [[ "$name" == xodus-reference-iso-* ]] || exit 95
       cp -a "$FIXTURE_DIR/core/." "$destination/"
       if [[ "${ADVANCE_MAIN_ON_CORE_DOWNLOAD:-0}" == 1 ]]; then
         cp "$FIXTURE_DIR/advanced-main.json" "$FIXTURE_DIR/main.json"
       fi ;;
  *) exit 96 ;;
esac
EOF
chmod +x "$tmp/bin/gh"
export PATH="$tmp/bin:$PATH"

pass() {
  local label="$1"
  shift
  if ! "$@" > "$tmp/result.log" 2>&1; then
    echo "FAIL: $label" >&2
    cat "$tmp/result.log" >&2
    exit 1
  fi
}

reject() {
  local label="$1"
  shift
  if "$@" > "$tmp/result.log" 2>&1; then
    echo "FAIL: $label was accepted" >&2
    exit 1
  fi
}

# The checksum records pearos-iso/<name>; the downloaded artifact is flat.
pass 'flat fetch' bash "$fetch" "$tmp/fetched-flat"
pass 'flat bundle' bash "$writer" --verify-bundle "$tmp/fetched-flat"
cmp "$FIXTURE_DIR/core/$iso_name" "$tmp/fetched-flat/$iso_name"
reject 'non-block target after valid bundle' bash "$writer" --dry-run "$tmp/fetched-flat" /dev/null
grep -Fq 'target is not a block device' "$tmp/result.log"

# A preserved subdirectory layout must verify too.
make_core "$tmp/nested" pearos-iso
cp "$FIXTURE_DIR/qualification/hardware-candidate.json" "$tmp/nested/"
pass 'nested bundle' bash "$writer" --verify-bundle "$tmp/nested"

make_core "$tmp/tampered" ''
cp "$FIXTURE_DIR/qualification/hardware-candidate.json" "$tmp/tampered/"
printf 'changed\n' >> "$tmp/tampered/$iso_name"
reject 'changed ISO' bash "$writer" --verify-bundle "$tmp/tampered"

make_core "$tmp/bad-checksum-path" ''
cp "$FIXTURE_DIR/qualification/hardware-candidate.json" "$tmp/bad-checksum-path/"
sed -i "s|pearos-iso/$iso_name|pearos-iso/Xodus-reference-other.iso|" "$tmp/bad-checksum-path/xodus-reference.sha256"
reject 'checksum for another ISO' bash "$writer" --verify-bundle "$tmp/bad-checksum-path"

make_core "$tmp/extra-checksum" ''
cp "$FIXTURE_DIR/qualification/hardware-candidate.json" "$tmp/extra-checksum/"
printf '%s  pearos-iso/%s\n' "$sha" "$iso_name" >> "$tmp/extra-checksum/xodus-reference.sha256"
reject 'multiple checksum lines' bash "$writer" --verify-bundle "$tmp/extra-checksum"

make_core "$tmp/extra-iso" ''
cp "$FIXTURE_DIR/qualification/hardware-candidate.json" "$tmp/extra-iso/"
cp "$tmp/extra-iso/$iso_name" "$tmp/extra-iso/Xodus-reference-extra.iso"
reject 'ambiguous ISO' bash "$writer" --verify-bundle "$tmp/extra-iso"

make_core "$tmp/wrong-producer" ''
cp "$FIXTURE_DIR/qualification/hardware-candidate.json" "$tmp/wrong-producer/"
sed -i "s/xodus_source_commit=$sha/xodus_source_commit=$upstream_sha/" "$tmp/wrong-producer/xodus-reference.manifest"
reject 'wrong producer source SHA' bash "$writer" --verify-bundle "$tmp/wrong-producer"

make_core "$tmp/wrong-artifact" ''
make_manifest "$tmp/wrong-artifact/hardware-candidate.json"
jq '.core_iso.artifact_name = "xodus-reference-iso-cccccccccccccccccccccccccccccccccccccccc"' \
  "$tmp/wrong-artifact/hardware-candidate.json" > "$tmp/changed.json"
mv "$tmp/changed.json" "$tmp/wrong-artifact/hardware-candidate.json"
reject 'artifact name disagrees with producer manifest' bash "$writer" --verify-bundle "$tmp/wrong-artifact"

make_core "$tmp/bad-policy" ''
make_manifest "$tmp/bad-policy/hardware-candidate.json"
jq '.policy = "live-boot-only-until-destructive-installer-vm-gate-passes"' "$tmp/bad-policy/hardware-candidate.json" > "$tmp/changed.json"
mv "$tmp/changed.json" "$tmp/bad-policy/hardware-candidate.json"
reject 'unknown policy in writer' bash "$writer" --verify-bundle "$tmp/bad-policy"

make_core "$tmp/bad-run" ''
make_manifest "$tmp/bad-run/hardware-candidate.json"
jq '.qa_qemu.run_id = "201"' "$tmp/bad-run/hardware-candidate.json" > "$tmp/changed.json"
mv "$tmp/changed.json" "$tmp/bad-run/hardware-candidate.json"
reject 'malformed run provenance in writer' bash "$writer" --verify-bundle "$tmp/bad-run"

jq '.policy = "unknown"' "$FIXTURE_DIR/qualification/hardware-candidate.json" > "$tmp/changed.json"
mv "$tmp/changed.json" "$FIXTURE_DIR/qualification/hardware-candidate.json"
reject 'unknown policy in fetcher' bash "$fetch" "$tmp/rejected-policy"
make_manifest "$FIXTURE_DIR/qualification/hardware-candidate.json"

printf 'changed\n' >> "$FIXTURE_DIR/core/$iso_name"
reject 'changed downloaded ISO' bash "$fetch" "$tmp/rejected-iso"
make_core "$FIXTURE_DIR/core" ''

jq '.head_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"' "$FIXTURE_DIR/qa-run.json" > "$tmp/changed.json"
mv "$tmp/changed.json" "$FIXTURE_DIR/qa-run.json"
reject 'wrong QA SHA' bash "$fetch" "$tmp/rejected-qa"
cat > "$FIXTURE_DIR/qa-run.json" <<EOF
{"head_sha":"$sha","status":"completed","conclusion":"success"}
EOF

cat > "$FIXTURE_DIR/advanced-main.json" <<EOF
{"commit":{"sha":"$upstream_sha"}}
EOF
reject 'main advance during download' env ADVANCE_MAIN_ON_CORE_DOWNLOAD=1 bash "$fetch" "$tmp/rejected-race"
grep -Fq 'main advanced while the candidate was downloaded' "$tmp/result.log"
[[ ! -e "$tmp/rejected-race/hardware-candidate.json" ]] || {
  echo 'FAIL: stale downloaded bundle retained its qualification manifest' >&2
  exit 1
}
cat > "$FIXTURE_DIR/main.json" <<EOF
{"commit":{"sha":"$upstream_sha"}}
EOF
reject 'stale qualification run after main advances' bash "$fetch" "$tmp/rejected-stale"
grep -Fq 'latest successful Hardware Candidate Gate run is stale' "$tmp/result.log"

mkdir "$tmp/existing-output"
reject 'pre-existing output' bash "$fetch" "$tmp/existing-output"

# Exercise the last-moment disk check without opening a real disk. The fake
# blockdev command swaps the input symlink after the first safety snapshot;
# both dd and sudo are stubs that record any attempted write.
mapfile -t block_targets < <(find /dev -maxdepth 1 -type b -print | sort)
if (( ${#block_targets[@]} >= 3 )); then
  export FIXTURE_FIRST_BLOCK="${block_targets[0]}"
  export FIXTURE_SECOND_BLOCK="${block_targets[1]}"
  export FIXTURE_ROOT_BLOCK="${block_targets[2]}"
  export FIXTURE_DEVICE_LINK="$tmp/swap-device"
  export FIXTURE_SWAP_DONE="$tmp/swap-done"
  export FIXTURE_DD_MARKER="$tmp/dd-invoked"
  ln -s "$FIXTURE_FIRST_BLOCK" "$FIXTURE_DEVICE_LINK"

  cat > "$tmp/bin/findmnt" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$FIXTURE_ROOT_BLOCK"
EOF
  cat > "$tmp/bin/lsblk" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == -snrpo && "$2" == NAME ]]; then
  printf '%s\n' "$FIXTURE_ROOT_BLOCK"
elif [[ "$1" == -nrpo && "$2" == NAME,MOUNTPOINT ]]; then
  printf '%s\n' "$3"
elif [[ "$1" == -dnro ]]; then
  case "$2" in
    TYPE) echo disk ;;
    MAJ:MIN)
      if [[ "$3" == "$FIXTURE_FIRST_BLOCK" ]]; then echo 7:0
      elif [[ "$3" == "$FIXTURE_SECOND_BLOCK" ]]; then echo 7:1
      else echo 7:2; fi ;;
    MODEL) echo 'Fixture USB' ;;
    SERIAL) echo 'fixture-serial' ;;
    SIZE) echo 1G ;;
    *) exit 90 ;;
  esac
else
  exit 91
fi
EOF
  cat > "$tmp/bin/blockdev" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == --getsize64 ]] || exit 90
echo 1073741824
if [[ "${SWAP_TARGET:-0}" == 1 && ! -e "$FIXTURE_SWAP_DONE" ]]; then
  ln -sfn "$FIXTURE_SECOND_BLOCK" "$FIXTURE_DEVICE_LINK"
  touch "$FIXTURE_SWAP_DONE"
fi
EOF
  cat > "$tmp/bin/dd" <<'EOF'
#!/usr/bin/env bash
touch "$FIXTURE_DD_MARKER"
exit 98
EOF
  cat > "$tmp/bin/sudo" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == -v ]]; then exit 0; fi
touch "$FIXTURE_DD_MARKER"
exit 98
EOF
  chmod +x "$tmp/bin/findmnt" "$tmp/bin/lsblk" "$tmp/bin/blockdev" "$tmp/bin/dd" "$tmp/bin/sudo"

  reject 'changed target with --yes' env SWAP_TARGET=1 bash "$writer" --yes "$tmp/fetched-flat" "$FIXTURE_DEVICE_LINK"
  grep -Fq 'target identity changed after confirmation' "$tmp/result.log"
  [[ ! -e "$FIXTURE_DD_MARKER" ]] || {
    echo 'FAIL: dd was invoked after target identity changed' >&2
    exit 1
  }
else
  echo 'SKIP: target-swap fixture needs three block device nodes' >&2
fi

echo 'candidate handoff contract: PASS'

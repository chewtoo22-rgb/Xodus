#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
overlay="$repo_root/overlay/apply-xodus-identity.sh"
lock="$repo_root/upstream/installer.lock"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

ref="$(sed -n 's/^REF=//p' "$lock" | tr -d '\r')"
blob="$(sed -n 's/^SETUP_BLOB=//p' "$lock" | tr -d '\r')"
[[ "$ref" =~ ^[0-9a-f]{40}$ && "$blob" =~ ^[0-9a-f]{40}$ ]]

make_fixture() {
  local root="$1"
  mkdir -p "$root/pear/airootfs/etc"
  cat > "$root/pear/profiledef.sh" <<'EOF'
iso_name="pearOS-NiceC0re"
iso_label="pearOS_NiceC0re_$(date +%Y%m)"
iso_publisher="The Pear Project <https://pearos.xyz>"
iso_application="pearOS Live Session"
file_permissions=()
EOF
  echo pearOS-Live-System > "$root/pear/airootfs/etc/hostname"
  cat > "$root/build-binary" <<'EOF'
#!/usr/bin/env bash
_make_custom_airootfs() {
    # Clone pearOS-installer from GitHub instead of using local files
    git clone --depth 1 https://github.com/pearOS-archlinux/pearOS-installer.git "${pacstrap_dir}/usr/share/pearOS-installer" || _msg_error "Failed to clone pearOS-installer from GitHub" 1
}
_make_pkglist() { :; }
_build_iso_base() {
    _run_once _make_customize_airootfs
    _run_once _make_pkglist
    if [[ "${buildmode}" == 'netboot' ]]; then
        _run_once _make_boot_on_iso9660
    else
        _run_once _make_bootmodes
    fi
    _run_once _cleanup_pacstrap_dir
    _run_once _prepare_airootfs_image
}
EOF
}

make_fixture "$tmp/good"
XODUS_SOURCE_COMMIT=0123456789abcdef0123456789abcdef01234567 \
XODUS_UPSTREAM_COMMIT=89abcdef0123456789abcdef0123456789abcdef \
  bash "$overlay" "$tmp/good" >/dev/null
builder="$tmp/good/build-binary"
info="$tmp/good/pear/airootfs/usr/lib/xodus/build-info"
grep -Fxq "XODUS_INSTALLER_COMMIT=$ref" "$info"
grep -Fq "fetch --depth=1 origin $ref" "$builder"
grep -Fq "rev-parse HEAD:system_install/setup" "$builder"
! grep -Fq 'git clone --depth 1 https://github.com/pearOS-archlinux/pearOS-installer.git' "$builder"
bash -n "$builder"

# Run the exact patched fetch block with a fake git command. Both commit and
# setup-blob checks must reject mismatches before an ISO can be produced.
awk '/^    git init -q / {copy=1} copy {print} /rev-parse HEAD:system_install\/setup/ {if (copy) exit}' \
  "$builder" > "$tmp/fetch-block.sh"
test "$(wc -l < "$tmp/fetch-block.sh")" -eq 6
bash -n "$tmp/fetch-block.sh"
mkdir -p "$tmp/bin" "$tmp/pacstrap/usr/share"
cat > "$tmp/bin/git" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$MOCK_GIT_LOG"
case "$*" in
  *' rev-parse HEAD') printf '%s\n' "$MOCK_HEAD" ;;
  *' rev-parse HEAD:system_install/setup') printf '%s\n' "$MOCK_BLOB" ;;
esac
EOF
chmod +x "$tmp/bin/git"
run_fetch_block() {
  PATH="$tmp/bin:$PATH" MOCK_GIT_LOG="$tmp/git.log" MOCK_HEAD="$1" MOCK_BLOB="$2" \
    pacstrap_dir="$tmp/pacstrap" bash -c '
      set -euo pipefail
      _msg_error() { echo "$1" >&2; exit "$2"; }
      source "$1"
    ' _ "$tmp/fetch-block.sh"
}
run_fetch_block "$ref" "$blob"
grep -Fq "fetch --depth=1 origin $ref" "$tmp/git.log"
if run_fetch_block 0000000000000000000000000000000000000000 "$blob" >"$tmp/bad-head.log" 2>&1; then
  echo 'ERROR: builder accepted the wrong installer commit' >&2
  exit 1
fi
if run_fetch_block "$ref" 0000000000000000000000000000000000000000 >"$tmp/bad-blob.log" 2>&1; then
  echo 'ERROR: builder accepted the wrong installer setup blob' >&2
  exit 1
fi

make_fixture "$tmp/drift"
sed -i 's/git clone --depth 1/git clone --branch main --depth 1/' "$tmp/drift/build-binary"
if bash "$overlay" "$tmp/drift" >"$tmp/drift.log" 2>&1; then
  echo 'ERROR: overlay accepted a changed upstream installer clone layout' >&2
  exit 1
fi
grep -Fq 'pinned upstream installer clone layout changed' "$tmp/drift.log"

echo 'installer source pin contract: PASS'

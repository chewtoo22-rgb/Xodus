#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
probe="$repo_root/overlay/live-desktop/xodus-live-desktop-probe"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin"

cat >"$tmp/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
[[ "$*" == 'is-active --quiet display-manager.service' && "${MOCK_SDDM:-yes}" == yes ]]
EOF
cat >"$tmp/bin/id" <<'EOF'
#!/usr/bin/env bash
[[ "$*" == '-u liveuser' ]] || exit 1
echo 1000
EOF
cat >"$tmp/bin/pgrep" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == '-u' && "$2" == 1000 && "$3" == '-x' ]] || exit 1
case "$4" in
  kwin_wayland) [[ "${MOCK_KWIN:-yes}" == yes ]] ;;
  kwin_x11) [[ "${MOCK_KWIN_X11:-yes}" == yes ]] ;;
  plasmashell) [[ "${MOCK_PLASMA:-yes}" == yes ]] ;;
  *) exit 1 ;;
esac
EOF
cat >"$tmp/bin/loginctl" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  show-user)
    [[ "$2" == liveuser ]] || exit 1
    echo 3
    ;;
  show-session)
    [[ "$2" == 3 ]] || exit 1
    cat <<DETAILS
Name=${MOCK_USER:-liveuser}
Active=${MOCK_ACTIVE:-yes}
State=${MOCK_STATE:-active}
Type=${MOCK_TYPE:-wayland}
Class=${MOCK_CLASS:-user}
Remote=${MOCK_REMOTE:-no}
DETAILS
    ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$tmp/bin/"*
export PATH="$tmp/bin:$PATH"

# Source the production probe so each case exercises its exact predicate.
source "$probe"
[[ $(desktop_session) == '3 wayland kwin_wayland' ]]
[[ $(MOCK_TYPE=x11 desktop_session) == '3 x11 kwin_x11' ]]
if MOCK_TYPE=x11 MOCK_KWIN_X11=no desktop_session >/dev/null; then
  echo 'probe falsely accepted X11 without its compositor' >&2
  exit 1
fi

for setting in \
  MOCK_SDDM=no MOCK_KWIN=no MOCK_PLASMA=no \
  MOCK_USER=other MOCK_ACTIVE=no MOCK_STATE=closing \
  MOCK_TYPE=tty MOCK_CLASS=greeter MOCK_REMOTE=yes; do
  name=${setting%%=*}
  value=${setting#*=}
  export "$name=$value"
  if desktop_session >/dev/null; then
    echo "probe falsely accepted $setting" >&2
    exit 1
  fi
  unset "$name"
done

fixture="$tmp/upstream"
mkdir -p "$fixture/pear/airootfs/etc"
cat >"$fixture/pear/profiledef.sh" <<'EOF'
iso_name="pearOS-NiceC0re"
iso_label="pearOS_NiceC0re_$(date +%Y%m)"
iso_publisher="The Pear Project <https://pearos.xyz>"
iso_application="pearOS Live Session"
file_permissions=()
EOF
echo 'pearOS-Live-System' >"$fixture/pear/airootfs/etc/hostname"
: >"$fixture/pear/airootfs/etc/motd"
cat >"$fixture/build-binary" <<'EOF'
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
python3 "$repo_root/qa/boot_identity_fixture.py" "$fixture"
bash "$repo_root/overlay/apply-xodus-identity.sh" "$fixture" >/dev/null
test -x "$fixture/pear/airootfs/usr/lib/xodus/xodus-live-desktop-probe"
test -f "$fixture/pear/airootfs/usr/lib/systemd/system/xodus-live-desktop-probe.service"
test "$(readlink "$fixture/pear/airootfs/etc/systemd/system/graphical.target.wants/xodus-live-desktop-probe.service")" = \
  /usr/lib/systemd/system/xodus-live-desktop-probe.service

# The pinned builder discards modes when copying airootfs. Confirm its
# file_permissions pass will restore every shipped Xodus executable.
(
  declare -A file_permissions=()
  source "$fixture/pear/profiledef.sh"
  for name in \
    xodus-hardware-live-evidence xodus-x1-nuc-preflight \
    xodus-build-info-verify xodus-first-boot xodus-ai-first-boot \
    xodus-ai-runtime-preflight.py xodus-live-desktop-probe; do
    test -f "$fixture/pear/airootfs/usr/lib/xodus/$name"
    test "${file_permissions[/usr/lib/xodus/$name]:-}" = '0:0:755'
  done
  if test -f "$fixture/pear/airootfs/usr/lib/xodus/xodus-ai-select.py"; then
    test "${file_permissions[/usr/lib/xodus/xodus-ai-select.py]:-}" = '0:0:755'
  fi
  test -z "${file_permissions[/usr/lib/xodus/build-info]:-}"
)

echo 'PASS: live desktop probe predicate and ISO overlay installation'

#!/usr/bin/env bash
set -euo pipefail

root=${1:-}
if [[ -z "$root" || ! -d "$root/pear/airootfs" ]]; then
  echo "usage: $0 <pearOS-iso-source-root>" >&2
  exit 64
fi

airoot="$root/pear/airootfs"
install -d "$airoot/usr/lib/xodus" "$airoot/usr/lib/systemd/system" "$airoot/etc/systemd/system/multi-user.target.wants"

install -m 0755 /dev/stdin "$airoot/usr/lib/xodus/xodus-firstboot-readiness" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
state_dir=${XODUS_FIRSTBOOT_STATE_DIR:-/var/lib/xodus/firstboot}
out="$state_dir/readiness.env"
mkdir -p "$state_dir"

root_source=${XODUS_TEST_ROOT_SOURCE:-$(findmnt -n -o SOURCE / 2>/dev/null || true)}
root_fstype=${XODUS_TEST_ROOT_FSTYPE:-$(findmnt -n -o FSTYPE / 2>/dev/null || true)}
case "$root_fstype" in
  overlay|squashfs|tmpfs|ramfs) echo "refusing first-boot readiness on live/volatile root: $root_fstype" >&2; exit 78 ;;
esac
case "$root_source" in
  airootfs|overlay|squashfs|'') echo "refusing first-boot readiness on non-installed root: ${root_source:-unknown}" >&2; exit 78 ;;
esac

uefi=0; [[ -d /sys/firmware/efi || ${XODUS_TEST_UEFI:-0} == 1 ]] && uefi=1
network=none
command -v NetworkManager >/dev/null 2>&1 && network=NetworkManager
command -v networkctl >/dev/null 2>&1 && [[ "$network" == none ]] && network=systemd-networkd
sound=0; [[ -d /proc/asound || ${XODUS_TEST_SOUND:-0} == 1 ]] && sound=1
gpu=unknown
for card in /sys/class/drm/card*/device/vendor; do
  [[ -r "$card" ]] || continue
  vendor=$(cat "$card")
  case "$vendor" in 0x8086) gpu=intel;; 0x10de) gpu=nvidia;; 0x1002) gpu=amd;; esac
  [[ "$gpu" != unknown ]] && break
done

umask 022
tmp="$out.tmp.$$"
cat > "$tmp" <<EOF2
XODUS_FIRSTBOOT_SCHEMA=1
XODUS_INSTALLED_ROOT_SOURCE=$root_source
XODUS_INSTALLED_ROOT_FSTYPE=$root_fstype
XODUS_UEFI=$uefi
XODUS_NETWORK_STACK=$network
XODUS_SOUND_PRESENT=$sound
XODUS_GPU_VENDOR=$gpu
XODUS_FIRSTBOOT_COMPLETE=1
EOF2
mv -f "$tmp" "$out"
printf 'xodus-firstboot: readiness recorded at %s\n' "$out"
EOF

cat > "$airoot/usr/lib/systemd/system/xodus-firstboot-readiness.service" <<'EOF'
[Unit]
Description=Xodus first-boot installed-system readiness probe
ConditionPathExists=!/var/lib/xodus/firstboot/readiness.env
After=local-fs.target
Before=graphical.target

[Service]
Type=oneshot
ExecStart=/usr/lib/xodus/xodus-firstboot-readiness
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

ln -sfn /usr/lib/systemd/system/xodus-firstboot-readiness.service "$airoot/etc/systemd/system/multi-user.target.wants/xodus-firstboot-readiness.service"

test -x "$airoot/usr/lib/xodus/xodus-firstboot-readiness"
test -L "$airoot/etc/systemd/system/multi-user.target.wants/xodus-firstboot-readiness.service"
echo "Installed Xodus first-boot readiness service"

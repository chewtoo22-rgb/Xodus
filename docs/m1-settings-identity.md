# Xodus Settings and About

`overlay/identity/settings` prepares and compiles the settings source at the exact Git commit and subtree recorded in `source.lock.json`. The Qt6 backends for device settings remain in the native application. Xodus owns the window, navigation, charcoal/purple/white palette, and the General and About pages. Search and navigation preserve the existing functional page indices.

The Xodus navigation contains the working device and desktop pages. Upstream cloud account sign-in, upstream cloud AI, and nonfunctional service placeholders are excluded from navigation and compilation. No Xodus cloud account service is implied. The General page links only to implemented settings pages. The About page shows the actual hostname, processor, memory, graphics, kernel and storage reported by the system.

## Build integration

1. Copy this entire overlay directory to the source profile as `pear/xodus-settings` before the build container starts.
2. Install `cmake ninja git python qt6-base qt6-declarative qt6-5compat qt6-shadertools qt6-svg libx11` in the Arch build container alongside the compiler. These are host build dependencies; the source is compiled in that container against its Qt6 libraries.
3. After packages and `customize_airootfs` run, invoke `bash "$profile/xodus-settings/build-settings.sh" "$profile" "$live_root"`, before the final visible-identity helper and squashfs generation. This ordering exposes the actual package-created executables and launchers to validation.
4. Retained image inventory must assert `/usr/lib/xodus/xodus-settings` is an executable ELF with mode 0755; `/usr/bin/systemsettings1` and `/usr/bin/system-overview` are the expected compatibility scripts; the existing Settings desktop ID points at Xodus; `/usr/lib/xodus/settings-source.json` matches the source lock; and `/usr/share/licenses/xodus-settings/{NOTICE,upstream-license.txt}` exist.

The existing `systemsettings1` menu command opens the rebuilt app. The `system-overview` command opens its About page with `--about`. The old standalone About application's broken npm route is replaced by this native view. Reusing the desktop file ID preserves existing dock pins.

The staging helper checks installed package versions and original entrypoints before replacing them. It runs `ldd` and an offscreen Qt Quick render inside the staged Arch root, with immediate dynamic symbol resolution. A missing Qt library, changed package layout or failed QML render stops the ISO build. The source commit is recorded inside the image. Upstream package license records remain present, and Xodus installs a separate source attribution notice.

## Verification

Run `python3 qa/test_settings_identity.py` on Linux for version, launcher, symlink, ABI and failed-render rejection cases. The native app accepts `--self-test --about` and exits after a successful render. For visual review, set `XODUS_SETTINGS_RENDER_PATH` to an absolute writable PNG path; `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Basic` provides a display-free rendering path.

Actual Settings actions still require runtime validation on the live desktop. An offscreen render validates QML startup and appearance; it does not prove Wi-Fi, display changes, fingerprint enrollment, updates or privileged settings actions. Full current-head ISO/desktop evidence remains the release gate.

On 2026-09-30 the prepared native source compiled successfully with GCC 15.2 and Qt 6.10.2 on Ubuntu WSL. The General and About pages rendered at 1040×720 and were visually reviewed. All six staging rejection/compatibility tests passed. That local review displays the WSL system version and hardware readings; it is separate from the required Arch live-root ABI check and ISO runtime screenshots.

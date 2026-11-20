# Xodus shell identity overlay

`overlay/identity/apply-shell-identity.sh` runs after package installation,
upstream customization, and `apply-visible-identity.sh`. It validates all
expected package files before writing any change. A missing file, changed
anchor, unknown localized Pear label, unsafe path, or competing SDDM theme
selection stops the build.

Stage `overlay/identity/shell/` beside the copied helper, or pass its staged
directory as the second argument:

```sh
bash "$profile/xodus-apply-shell-identity.sh" "$pacstrap_dir" "$profile/xodus-shell"
```

The helper presents Xodus widget names, menu logo, About label, Files tooltip,
app title defaults, dock/clock/calendar/control center labels, selectable
theme labels, window border and sound theme labels, hardcoded launcher icons, and Notch launcher metadata. Both `/etc/skel` and the already
created `/home/liveuser` receive the lock wallpaper, Xodus color scheme,
purple accent, and Noto Sans fonts. The original Xodus SDDM login theme is
installed at `/usr/share/sddm/themes/Xodus` and selected by
`/etc/sddm.conf.d/20-xodus-theme.conf`. It supports enumerated and manual
accounts, session selection, failed authentication feedback, empty password
submission for PAM to decide, and SDDM's restart/shutdown actions.

The session splash is an original QtQuick layout with actual Plasma stage
progress. It replaces the two installed splash QML files while preserving
their runtime package IDs and upstream metadata attribution. Xodus original
login, splash and color scheme sources are under MIT; their license is
installed at `/usr/share/licenses/xodus-shell/LICENSE`.

Upstream plugin IDs, executable names and attribution remain where runtime
compatibility needs them. Package authors, source URLs and licenses are
retained. The helper leaves SDDM autologin and authentication configuration
intact; live autologin bypasses the account screen.

## Package evidence and checks

The helper was exercised on the real archives used by the retained Core ISO
build, downloaded from the configured pearOS package mirror on September 30,
2026. Fixture extraction reads regular text files only and executes no
package code.

| Archive | SHA-256 |
| --- | --- |
| `pearos-settings-26.7.0-4-x86_64.pkg.tar.zst` | `d2f993265cea5d7dffb8d3557ee9768e98bc796f95e907cb05840cb5a8b241e9` |
| `pearos-dock-26.6.10-5-x86_64.pkg.tar.zst` | `662cda638466461cd0a5d5c58385bb85308b4ecfa15306d6d26e173579bbfac5` |
| `pearos-notch-26.6.1-1-x86_64.pkg.tar.zst` | `4251b0c484f9037a7ee306eb5696867d18039323a2216ee7bdd75cc2619b6b73` |

Run the package contract on Linux with Python 3.14, whose tarfile module
supports zstd:

```sh
python3 qa/shell-identity-package-contract.py settings.pkg.tar.zst dock.pkg.tar.zst notch.pkg.tar.zst
```

It checks successful output and verifies that late metadata drift,
unreviewed localized branding, and conflicting SDDM selection leave every
fixture file unchanged. The real package fixture produces 64 updated or
installed files. This found a package/source mismatch in the smallest font
serialization before the helper was integrated into the ISO.

`qa/shell-qml-contract.py` requires PySide6. It loads the real QML in QtQuick,
renders login at 1920×1080, 1280×720, 800×600 and 640×480, and checks account
and session forwarding, manual and unenumerated accounts, busy state, failed
login, empty password, power actions, and session splash completion.

```sh
python3 qa/shell-qml-contract.py --output /tmp/xodus-shell-renders
```

The local render used Qt/PySide6 6.9.3 on the offscreen software backend,
with the current Xodus black/purple artwork. Windows offscreen Qt has no
system font enumeration, so a locally loaded Arial TTF was supplied through
`--font` as a render substitute. The deployed theme requests Noto Sans,
already included by the ISO's `noto-fonts` package. Render checks are theme
and API checks; the installed ISO must still prove real SDDM/PAM sign in,
session launch, logout, lock/unlock, scaling, and keyboard navigation.

## Surfaces requiring additional work

This overlay is one portion of the full graphical redesign. Widget internals
and upstream SVG window/panel styling still need visual review in the built
image. The installed icon set, cursor set, sound theme, Kvantum styling and
window decoration retain their upstream runtime identifiers. Legal
attribution and source/package identities are not visible product labels.

Compiled application strings require rebuilding their sources. Installed
`system-settings-26.7.0-1` provides `/usr/bin/systemsettings1` and
`/usr/share/applications/pearos-systemsettings.desktop`; its Qt6 QML and C++
sources are in `pearOS-archlinux/pkgbuilds/pearos-settings-app`.
`system-overview-26.3-1` provides `/usr/bin/system-overview`; its sources
are under `pearOS-archlinux/pkgbuilds/pearos-about/pearos-about`. The menu
continues to use those installed command names so source replacements can
retain their established launch contract.

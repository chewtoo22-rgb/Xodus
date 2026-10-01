# Xodus GTK and terminal appearance

Original charcoal, purple and white GTK themes, Noto Sans typography and readable
Konsole palettes complement the Xodus Plasma shell. Light mode uses the same
purple accents with pale surfaces. The glass terminal has opacity 0.94; the
standard terminal is opaque. ANSI red/green/yellow/blue distinctions remain.

## Reviewed inputs

`source.lock.json` pins the actual archives and 29 selected package files:

- `pearos-settings` 26.7.0-4, SHA256
  `d2f993265cea5d7dffb8d3557ee9768e98bc796f95e907cb05840cb5a8b241e9`.
- `system-settings` 26.7.0-1, SHA256
  `dfc36d4b044793485559f73caea0f9dc2eb032a233b95afa5d48e8dcc1d33024`.

All bytes are checked before mutation. Only the existing GTK light/dark selector
and boolean preference may vary in the package template. GTK2's original Light
selection and GTK3/4's original Dark selections are retained individually.
Font, modules, commands and other source fields must match the audit.

Reviewed originals are retained under
`/usr/share/licenses/xodus-toolkit/upstream/`. Existing package licenses stay in
place. Original Xodus themes, palettes and runtime helper use the accompanying
MIT license; derived upstream scripts retain their package GPLv3 obligations.

## Builder order and verification

After package installation, Settings and shell identity application, run:

```sh
python3 overlay/identity/toolkit/apply-toolkit-identity.py "$live_root"
```

Then apply the separately audited desktop defaults helper for Breeze icons,
cursor, window decoration and Qt widget style. Capture the installed identity
manifest after both helpers, while preserving mode 0755 on the runtime helper
and derived executable scripts.

The toolkit helper leaves initial `kdeglobals`, `kwinrc`, `kcminputrc`, `plasmarc`
and GTK icon/cursor/decoration fields for that desktop helper. Its verifier
accepts only exact alternative GTK bytes with `breeze` or `breeze-dark`,
`breeze_cursors` and `:minimize,maximize,close`; every other byte stays fixed.

```sh
python3 overlay/identity/toolkit/apply-toolkit-identity.py "$live_root" --verify
python3 overlay/identity/toolkit/apply-toolkit-identity.py --list-transfer-files
python3 overlay/identity/toolkit/apply-toolkit-identity.py --list-reference-files
```

Importable integration API:

- `verify(root, payload=None)` recomputes outputs from pinned retained originals
  and trusted repository source assets. `payload` is the toolkit source directory.
- `TRANSFER_FILES`: exact closed system, original-notice and skeleton paths.
- `USER_CONFIGS`: the twelve home-relative skeleton identity paths.
- `REFERENCE_FILES`: the eight source paths required to reproduce verification.
- `EXECUTABLE_FILES`: runtime and derived executable paths requiring mode 0755.

The receipt `/usr/lib/xodus/toolkit-source.json` is compared with a freshly
derived receipt. Editing payload bytes and updating receipt hashes is rejected.
Verification never executes the theme switcher or any desktop command.

System payloads include six files each under `/usr/share/themes/Xodus-Dark/` and
`Xodus-Light/`, four `/usr/share/konsole/Xodus*.colorscheme` files, the mode helper,
derived theme-switcher scripts/configuration and ten accent presets plus
`colors.json`. The generated path list is authoritative for installed transfer
and ISO extraction. Live-user account files, hostname, machine IDs, login
configuration and dynamic theme-switcher state/accent records are excluded.

## Automatic switching and installed accounts

Existing `pearos-theme-light/dark.service` compatibility IDs continue invoking
the same `kde-theme-switch.sh` path and `--light`/`--dark` arguments. The script
selects `Xodus`/`Xodus Light` KDE color schemes, `default` Plasma, Breeze widgets,
icons and cursor, and `Xodus-Dark`/`Xodus-Light` GTK themes. No active Aurorae or
Kvantum reset is introduced. Root's desktop defaults choose `org.kde.breeze`.

`/usr/lib/xodus/apply-user-toolkit-mode --mode light|dark` changes only GTK
appearance keys and the color-scheme key in the two shipped Konsole profiles.
GTK application modules, toolbar behavior and other settings remain. Profile
filenames and Konsole's selected profile ID remain compatible; `/bin/zsh`,
parent profile behavior and custom terminal palette choices remain. The helper
checks all destinations before writing and rejects symlink/hardlink paths.

The automatic script updates the Dock through Plasma's existing API, using
`Xodus Light` and `Xodus Dark` under the compatible internal `PearDock` ID.
It preserves custom wallpaper paths, including personal files named
`default.jpg`; reviewed upstream wallpaper paths resolve to the Xodus wallpaper.
GTK4 CSS remains a regular file rather than being replaced with old theme
symlinks, and changing mode no longer forcibly closes Nautilus. Accent presets
contain only palette and accent keys; they cannot restore old schemes, device
settings or sample account history.

Runtime requirements are Python3, the existing Plasma commands and `qdbus6`
from `qt6-tools` for Dock updates. `noto-fonts` supplies Noto Sans and Noto Sans
Mono. Runtime dependencies must be checked in both the live and installed root.

After the installer's one-time first-theme setup, the installed identity restore
hook must preserve the selected light/dark mode while restoring these twelve
skeleton paths, then apply that mode once. Later logins must not reset user
choices. Do not add toolkit defaults to an every-login reset.

## Disposable QA and visual review

```sh
python3 qa/toolkit-identity-contract.py \
  --package /path/to/pearos-settings-26.7.0-4.pkg.tar.zst \
  --switcher-package /path/to/system-settings-26.7.0-1.pkg.tar.zst
xvfb-run -a python3 overlay/identity/toolkit/preview-toolkit.py \
  --gtk 3 --mode Dark --output /var/tmp/xodus-gtk3-dark.png
xvfb-run -a python3 overlay/identity/toolkit/preview-toolkit.py \
  --gtk 4 --mode Light --adwaita --output /var/tmp/xodus-adwaita-light.png
```

Twelve package-backed contracts cover deterministic derivation, source drift,
independent receipt verification, mode preferences, paths and permissions,
automatic switching, accent changes and unchanged account/command/module data.
Native widget previews were rendered with GTK 3.24.52, GTK 4.22.4 and libadwaita
1.9.1 in Light and Dark modes; all supplied CSS parsed without errors. Main,
view and selected text colors meet 4.5:1 contrast in both generated palettes.

GTK2 uses the standard engine and has simpler geometry than GTK3/4. Libadwaita
owns its application surfaces; the user stylesheet supplies Xodus accents,
typography and controls while retaining libadwaita's mode preference. Apps with
their own stylesheets may override toolkit styling. These disposable tests do
not establish ISO release readiness or an actual disk installation result.

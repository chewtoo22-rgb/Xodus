# Xodus dock appearance

`Xodus Light` and `Xodus Dark` are the only runtime skin IDs. The internal
`PearDock` plugin ID, task model, launch actions, grouping, drag/drop and audio
controls retain their package interfaces. Original Xodus QML and SVG artwork
uses violet accents with neutral light and dark surfaces. The dock's existing
blur, refraction and margin overrides remain functional.

`frame.svg` is the editable original. `frame.png` is its QtSvg export used by
the package's `BorderImage`; it does not require the optional SVG image plugin.
`tasks.svg` supplies all nine frame pieces for eight states, each with base,
north, south, east and west prefixes. The old four skin directories and their
readmes move intact to `usr/share/licenses/xodus-dock/upstream-skins`.

## Builder integration

Stage this complete directory beside the helper. Run after the base shell
identity pass and before installed payload capture:

```sh
python3 pear/xodus-dock/apply-dock-identity.py "$live_root"
python3 pear/xodus-dock/apply-dock-identity.py "$live_root" --verify
```

`source.lock.json` pins package `pearos-dock 26.6.10-5`, its archive SHA256,
three complete source files, all 27 old skin files and the reviewed three
patched source hashes. Every source and preference edit is checked before
mutating the package. New user presets use the XML default `Xodus Dark`.
Explicit old light/dark skin preferences migrate while preserving other keys.

`--list-installed-files` and importable `TRANSFER_FILES` supply the closed
41 file installed/ISO whitelist. `USER_CONFIGS` lists the skeleton and liveuser
panel preferences. `verify(root, payload=...)` returns a deterministic dictionary
with 40 actual output SHA256 values. It compares actual source files against the
repo lock and actual artwork against repo bytes, independently of the payload's
`usr/lib/xodus/dock-source.json`. It rejects old/competing selectable skin folders,
altered files and unsafe symlinks. Absence checks need the extracted runtime
`contents/skins` directory to include its full listing.

The retained verifier needs these twelve reference files in original layout:
the helper, `source.lock.json`, `NOTICE`, `ui/XodusSkinSelector.qml`, and both
`skins/Xodus */{Config.qml,frame.svg,frame.png,tasks.svg}` sets (12 total).
`README.md` is documentation and need not be staged for the retained checker.

Settings preparation copies the native `AppearancePage.qml` overlay and patches
the pinned `dockmanager.cpp/.h`: only Xodus skin names are listed or written.
The rest of that backend remains unchanged. Light, dark and automatic buttons
write these exact IDs. The toolkit theme-switcher also writes them from the
existing 08:00/18:00 services, including while Settings is closed. Native accent
changes keep Breeze/Breeze Dark icons and preserve the existing KDE accent API.

## Acceptance

```sh
python3 qa/test_dock_identity.py
XODUS_PREPARED_SETTINGS=/path/to/prepared python3 qa/test_dock_settings_source.py
python3 qa/dock-identity-package-contract.py /path/to/pearos-dock-26.6.10-5.pkg.tar.zst
bash qa/dock-qml-contract.sh /path/to/prepared /path/to/render-output
```

`qa/dock-render-acceptance.cpp` is a Qt6 QuickTest setup for
`qa/tst_dock_appearance.qml`. It supplies controlled backend objects to the
actual native Appearance page, exercises mouse and keyboard button actions,
tests the dock selector's signal and external state updates, renders both
`BorderImage` frames in all four orientations, and renders actual task SVG
elements with QtSvg. Give `XODUS_SETTINGS_PAGE` the prepared native page path,
provide its native components with a local singleton Theme qmldir, and set
`XODUS_RENDER_DIRECTORY` to a disposable output directory. This controlled
acceptance does not substitute for Plasma/installer ISO runtime gates.

To export the original frames, compile `qa/dock-frame-export.cpp` with Qt6Gui
and Qt6Svg, then pass `frame.svg frame.png`. The source and rendered PNG are
both retained and hash checked.

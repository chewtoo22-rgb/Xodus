# Xodus Control Center

The Control Center now presents an original charcoal and purple control panel
with white text, original line glyphs, connectivity cards, a media strip,
brightness and volume controls, and clear session actions. Its active layout and
layout selector use Xodus. The original Tahoe, Flat and other layouts remain in
the package for provenance; they are not selected or offered by the new frontend.
The popup retains its 460px width and caps its height against the current screen's
available height, with a 96px allowance for the panel and screen margins. Its
content scrolls vertically when constrained. Keyboard focus scrolls the selected
control into view, including Power on a 600px desktop.

## Source and order

The reviewed source is `pearos-settings 26.7.0-4`, SHA-256
`d2f993265cea5d7dffb8d3557ee9768e98bc796f95e907cb05840cb5a8b241e9`.
`source.lock.json` pins all 102 original plasmoid files, including its service
components, controller pages, JavaScript, attribution and assets. Metadata must
already contain the base shell hook's Xodus Name and Description.

Stage the complete `overlay/identity/control-center/` directory, including its
helper, source lock and payload, then run after `apply-shell-identity.sh`:

```sh
python3 /staged/control-center/apply-control-center-identity.py /live-root
python3 /staged/control-center/apply-control-center-identity.py /live-root --verify
```

All package and payload checks happen before writes. The helper rejects extra
files, changed controller source, package drift and symlinks. It modifies nine
reviewed frontend files and adds eight files. Existing service handlers remain
byte for byte; four components receive public frontend APIs after their original
code. Network, Bluetooth, notification, MPRIS, audio, brightness, device and
session pages continue to own their existing services. Power opens the existing
session action page. The new panel does not directly shut down the machine.

## Retained verification and installed transfer

Import the trusted helper and call `verify(root, payload=trusted_payload_dir)`.
Verification compares all 110 deployed plasmoid files against the reviewed
source-derived hashes and checks the exact derivation receipt at
`usr/share/xodus/identity/control-center.json`. It rejects controller drift and a
forged receipt.

The helper exports `TRANSFER_FILES`, a closed tuple of 111 paths: all original
providers, pages, JavaScript, attribution and assets, the eight new frontend
files, and the receipt. Installed identity transfer must carry this complete
tuple. The original service implementations are needed by `Controller.qml`.
`MINIMAL_REFS` lists the existing theme switch script and state file outside the
plasmoid; the screenshot and device tools remain distribution dependencies.

The 17 frontend paths relative to the plasmoid's `contents/` directory are:

- `config/main.xml`
- `ui/main.qml`, `ui/FullRepresentation.qml`, `ui/CompactRepresentation.qml`
- `ui/config/configAppearance.qml`
- `ui/components/NetworkBtn.qml`, `ui/components/DndButton.qml`
- `ui/components/Volume.qml`, `ui/components/BrightnessSlider.qml`
- `ui/layouts/Xodus.qml`
- `ui/xodus/ControlPanel.qml`, `ui/xodus/Controller.qml`, `ui/xodus/Glyph.qml`
- `ui/xodus/ActionButton.qml`, `ui/xodus/ControlTile.qml`, `ui/xodus/LevelControl.qml`
- `assets/xodus-controls.svg`

## Verification

```sh
python3 qa/control-center-package-contract.py /path/to/pearos-settings-26.7.0-4.pkg.tar.zst
python3 qa/control-center-qt-contract.py --render-dir /path/to/previews
```

The package contract verifies the exact archive, preserved service handlers and
legal metadata, defaults, the transfer tuple, deployed controller hashes,
receipt rejection, unexpected files and symlinks. The Qt contract renders the
actual shipped QML and controller adapter under Qt 6 with controlled providers.
It exercises Wi-Fi and Bluetooth toggles/details, MPRIS transport controls,
mouse and keyboard sliders, focus, display warmth, appearance, devices,
screenshot, power confirmation, battery details, optional commands and close.
It also renders unavailable-device states and verifies their controls disable.
The fixtures cannot execute commands or change hardware or a session.

These checks verify the frontend and adapter boundary. A current ISO running
Plasma is still required to verify the real KDE providers and hardware.

## Separate remaining graphics

The inherited Dock still exposes Big Sur and Tahoe skins and loads the original
skin graphics. GTK and Konsole selector names, icon/cursor graphics and window
decorations are separate surfaces. The native Notch still uses its original
silhouette and presented Dynamic Island/Notch names. Its actively drawn embedded
SVGs are generic house, tray, globe, gear and media glyphs; no pear or Apple logo
was found there. The old package launcher PNG contains an Apple logo, but the
current Xodus desktop entry selects the Xodus icon. Those findings do not imply
a complete OS graphical redesign.

# Xodus M1 visual identity

The Xodus desktop artwork now follows the user-supplied 10-second boot sequence: near-black (`#050508`), a dark X silhouette, purple backlight, and restrained white highlights. The geometric X keeps its open diamond. Its focal point stays on the right; the left and middle remain clear for windows, desktop icons, and readable labels. The standalone mark and application tile use white-to-violet accents so they remain legible at small sizes.

## Assets

| File | Purpose | Size |
| --- | --- | --- |
| `overlay/identity/assets/xodus-wallpaper.svg` | Editable wallpaper source | 3840 × 2160 SVG |
| `overlay/identity/assets/xodus-wallpaper.png` | Desktop wallpaper for the live image and installed system | 2560 × 1440 PNG |
| `overlay/identity/assets/xodus-mark.svg` | Transparent standalone mark for dark surfaces and scalable branding | 512 × 512 SVG |
| `overlay/identity/assets/xodus-app-icon.svg` | Editable application tile source | 512 × 512 SVG |
| `overlay/identity/assets/xodus-app-icon.png` | Installer/launcher icon with transparent rounded corners | 512 × 512 RGBA PNG |

The SVG files are the sources of record. The PNGs are deployment exports. The shapes, gradients, and orbital lines were drawn for Xodus; no third-party bitmap, font, logo, or icon is embedded. Upstream attribution remains a separate build and documentation responsibility.

## Usage

- Use `xodus-wallpaper.png` for Plasma wallpaper configuration. It is a 16:9 image; scale it proportionally on other displays. The artwork's focal point is on the right, so centered cropping on narrow screens should be reviewed before shipping.
- Use `xodus-app-icon.png` when a raster icon is required, including the installer icon in `/usr/share/pixmaps`. Its transparent corners are intentional. Use the SVG variant where scalable icons are supported.
- Use `xodus-mark.svg` without a tile on dark backgrounds. Use the application tile on light or visually busy backgrounds.
- Keep the visible X clear of labels and controls. Do not stretch either icon nonproportionally.

The left and middle 60% of the exported wallpaper were sampled on a 5 × 5 grid against `#F4F8FF` text and measured at 17.17:1 to 18.96:1 contrast. This describes those sample points; deployment should still use Plasma's normal text shadow for desktop labels.

## Export and review

The PNGs were rendered from the SVGs with the bundled Node `sharp` renderer: wallpaper at 2560 × 1440 and application icon at 512 × 512. Both source SVGs parse as XML. The wallpaper and icon were visually inspected after export; the icon remains readable at small sizes. Re-export the PNGs if their SVG sources change.

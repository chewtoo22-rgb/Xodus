# Xodus M1 visual identity

The first Xodus desktop artwork uses a calm midnight field and a geometric X with an open diamond at its center. The right side carries the signal; the left and middle stay quiet for windows, desktop icons, and readable labels. The palette is navy (`#071322`, `#0B1B2F`), cyan (`#75F2EF`), blue (`#49B8E9`), violet (`#AD85F5`), and a small amber accent (`#E9BD82`).

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

The left and middle 60% of the exported wallpaper were sampled against `#F4F8FF` text and measured at approximately 15.5:1 to 17.4:1 contrast. This describes the current image at those sampled points; deployment should still use Plasma's normal text shadow for desktop labels.

## Export and review

The PNGs were rendered from the SVGs with Google Chrome 153.0.8010.53 in headless mode. The wallpaper was fitted into a 2560 × 1440 viewport before capture. The application icon was captured directly from its SVG at 512 × 512 with a transparent browser background. Both source SVGs parse as XML. The wallpaper was visually inspected at 1920 × 1080 and 2560 × 1440, and the icon was checked at 128, 64, and 32 pixels on both light and dark backgrounds. The SVG source should be re-exported if its design changes.

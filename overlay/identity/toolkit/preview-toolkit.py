#!/usr/bin/env python3
"""Render real GTK widgets under Xvfb for toolkit visual/parser review."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import gi

os.environ.setdefault('GDK_BACKEND', 'x11')
os.environ.setdefault('GSK_RENDERER', 'cairo')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gtk', choices=('3', '4'), default='3')
parser.add_argument('--mode', choices=('Dark', 'Light'), default='Dark')
parser.add_argument('--output', type=Path)
parser.add_argument('--adwaita', action='store_true')
parser.add_argument('--parse-only', action='store_true')
parser.add_argument('--capture', nargs=3)
args = parser.parse_args()
if args.capture:
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk
    Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), 0, 0, int(args.capture[1]), int(args.capture[2])).savev(args.capture[0], 'png', [], [])
    raise SystemExit(0)

gi.require_version('Gtk', args.gtk + '.0')
from gi.repository import Gtk, Gdk, GLib
if args.gtk == '3':
    Gtk.init([])
else:
    Gtk.init()
if args.adwaita:
    gi.require_version('Adw', '1')
    from gi.repository import Adw
    Adw.init()
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if args.mode == 'Dark' else Adw.ColorScheme.FORCE_LIGHT)

source = Path(__file__).resolve().parent
errors = []
providers = []
module = __import__('runpy').run_path(str(source / 'apply-toolkit-identity.py'))
stylesheets = [module['css'](args.mode, args.gtk), (source / ('user-gtk' + args.gtk + '.css')).read_bytes()]
if args.adwaita:
    stylesheets = stylesheets[1:]
for data in stylesheets:
    provider = Gtk.CssProvider()
    provider.connect('parsing-error', lambda p, section, error: errors.append(str(error)))
    provider.load_from_data(data)
    if args.gtk == '3':
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    else:
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    providers.append(provider)
if errors:
    raise SystemExit('\n'.join(errors))
if args.parse_only:
    print('Parsed GTK' + args.gtk + ' ' + args.mode + (' libadwaita' if args.adwaita else ' Xodus') + ' CSS')
    raise SystemExit(0)
if not args.output:
    parser.error('--output required for rendering')

window = Adw.Window() if args.adwaita else Gtk.Window()
window.set_default_size(760, 520)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
for side in ('top', 'bottom', 'start', 'end'):
    getattr(box, 'set_margin_' + side)(24)
def add(container, widget, expand=False):
    if args.gtk == '3':
        container.pack_start(widget, expand, expand, 0)
    else:
        widget.set_vexpand(expand)
        container.append(widget)

heading = Gtk.Label(label='Xodus  /  ' + args.mode + ' appearance')
heading.set_xalign(0)
add(box, heading)
subtitle = Gtk.Label(label='Your workspace, in a quieter palette.')
subtitle.set_xalign(0)
add(box, subtitle)
entry = Gtk.Entry()
entry.set_text('Search applications and settings')
add(box, entry)
listing = Gtk.ListBox()
for label in ('Workspace          Noto Sans typography', 'Appearance        Purple accents and clear controls', 'Terminal              Readable ANSI colors'):
    row = Gtk.Label(label=label)
    row.set_xalign(0)
    listing.add(row) if args.gtk == '3' else listing.append(row)
listing.select_row(listing.get_row_at_index(1))
add(box, listing, True)
progress = Gtk.ProgressBar()
progress.set_fraction(.68)
add(box, progress)
actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
add(actions, Gtk.Button(label='Cancel'))
button = Gtk.Button(label='Continue')
button.get_style_context().add_class('suggested-action') if args.gtk == '3' else button.add_css_class('suggested-action')
add(actions, button)
switch = Gtk.Switch()
switch.set_active(True)
add(actions, switch)
add(box, actions)
if args.adwaita:
    window.set_content(box)
elif args.gtk == '3':
    window.add(box)
else:
    window.set_child(box)
window.show_all() if args.gtk == '3' else window.present()
loop = GLib.MainLoop()
def capture():
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(Path(__file__).resolve()), '--capture', str(args.output), '760', '520'], check=True)
    loop.quit()
    return False
GLib.timeout_add(700, capture)
loop.run()
print(args.output)

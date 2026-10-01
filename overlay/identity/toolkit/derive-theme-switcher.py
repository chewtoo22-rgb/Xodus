#!/usr/bin/env python3
"""Narrow appearance edits to the package-pinned automatic theme switcher."""
import json
import configparser
import io
import re

BASE = 'usr/share/extras/system-settings/themeswitcher/'
SCRIPTS = tuple(BASE + name for name in ('kde-theme-switch.sh', 'config.json', 'config.py', 'libadwaita'))
PRESETS = tuple(BASE + 'colors/' + name + '.ini' for name in (
    'azul', 'blue', 'dark-purple', 'green', 'grey', 'lila', 'magenta', 'orange', 'purple', 'yellow'))
FILES = (*SCRIPTS, *PRESETS, BASE + 'colors.json')


def config():
    return {mode: {
        'colorScheme': 'Xodus' if mode == 'dark' else 'Xodus Light',
        'plasmaTheme': 'default', 'iconTheme': 'breeze-dark' if mode == 'dark' else 'breeze',
        'cursorTheme': 'breeze_cursors', 'auroraeTheme': 'org.kde.breeze',
        'kvantumTheme': '', 'gtkTheme': 'Xodus-' + mode.title(),
        'sddmTheme': 'Xodus', 'appStyle': 'Breeze',
    } for mode in ('light', 'dark')}


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('audited theme-switcher anchor changed: ' + old[:80])
    return text.replace(old, new, 1)


def derive(relative, data):
    text = data.decode()
    if relative in PRESETS:
        upstream = configparser.ConfigParser(interpolation=None)
        upstream.optionxform = str
        upstream.read_string(text)
        reviewed = configparser.ConfigParser(interpolation=None)
        reviewed.optionxform = str
        for group in upstream.sections():
            if group.startswith('Colors:'):
                reviewed[group] = dict(upstream[group])
            elif group == 'General':
                reviewed[group] = {key: upstream[group][key] for key in ('AccentColor', 'LastUsedCustomAccentColor')}
        output = io.StringIO()
        reviewed.write(output, space_around_delimiters=False)
        return output.getvalue().encode()
    if relative == BASE + 'colors.json':
        return data
    if relative.endswith('config.json'):
        return (json.dumps(config(), indent=2) + '\n').encode()
    if relative.endswith('config.py'):
        start, end = text.index('DEFAULT_CONFIG = {'), text.index('\n\n# Discovery helpers')
        text = text[:start] + 'DEFAULT_CONFIG = ' + repr(config()) + text[end:]
        text = once(text, 'self.master.title("pearOS Theme Config")', 'self.master.title("Xodus Theme Configuration")')
        text = once(text, 'lambda: ["kvantum", "kvantum-light", "kvantum-dark"]', 'lambda: ["Breeze", "Fusion"]')
        text = text.replace('return sorted(uniq(names))', 'return sorted(name for name in uniq(names) if not name.lower().startswith("pearos"))')
        text = once(text, 'if key == "auroraeTheme":', 'if key == "auroraeTheme" and value != "org.kde.breeze":')
        return text.encode()
    if relative.endswith('libadwaita'):
        # The original functions forcibly closed Nautilus and replaced GTK4 CSS with
        # private pearOS theme symlinks. Keep the CLI/menu and apply just mode keys.
        for mode in ('dark', 'light'):
            start = text.index('apply_theme_' + mode + '() {')
            end = text.index('\n}', start) + 2
            body = 'apply_theme_' + mode + '() {\n    /usr/lib/xodus/apply-user-toolkit-mode --mode ' + mode + '\n'
            body += '    if command -v gsettings >/dev/null 2>&1; then\n'
            body += '        gsettings set org.gnome.desktop.interface color-scheme ' + ('prefer-dark' if mode == 'dark' else 'default') + ' || true\n'
            body += '    fi\n}\n'
            text = text[:start] + body + text[end:]
        return text.encode()
    if not relative.endswith('kde-theme-switch.sh'):
        raise ValueError('unreviewed switcher transform: ' + relative)
    text = once(text, 'KWIN_DECORATION_PLUGIN="org.kde.kwin.aurorae"', 'KWIN_DECORATION_PLUGIN="org.kde.breeze"')
    # Wallpaper changes apply only to reviewed defaults, leaving personal images.
    start, end = text.index('  case "$current_base" in'), text.index('  msg "DEBUG mode:', text.index('  case "$current_base" in'))
    text = text[:start] + '''  case "$current" in
    /usr/share/wallpapers/Xodus/xodus-wallpaper.png|/usr/share/extras/wallpapers/Default/dark-mode.jpg|/usr/share/extras/wallpapers/Default/light-mode.jpg|/usr/share/wallpapers/pearOS/default.jpg|/usr/share/wallpapers/pearOS-dark/default.jpg)
      target="/usr/share/wallpapers/Xodus/xodus-wallpaper.png"
      ;;
    *) return 0 ;;
  esac
''' + text[end:]
    text = text.replace('set_wallpaper_if_pearos', 'set_wallpaper_if_xodus')
    text = once(text, 'for k in COLOR PTHM ITHM CTHM KVT GTK SDDM AUR_THEME APPSTYLE;',
                'for k in COLOR PTHM ITHM CTHM GTK APPSTYLE;')
    text = once(text, 'cfg_write kdeglobals KDE widgetStyle "kvantum"', 'cfg_write kdeglobals KDE widgetStyle "$APPSTYLE"')
    # Accent presets change palette keys, preserving the selected mode. Reapplying
    # the entire scheme afterward would discard the accent just chosen.
    text = once(text, 'if [ -n "$cs_val" ] && have plasma-apply-colorscheme; then',
                'if [ -n "$cs_val" ] && have kwriteconfig6; then')
    text = once(text, 'msg "Re-apply color scheme after accent: $cs_val"', 'msg "Keep color scheme mode after accent: $cs_val"')
    text = once(text, 'plasma-apply-colorscheme "$cs_val" || true', 'cfg_write kdeglobals General ColorScheme "$cs_val" || true')
    start = text.index('  if [ -n "${KVT:-}" ]; then')
    end = text.index('  msg "Set GTK theme', start)
    text = text[:start] + '  # Xodus uses the Breeze Qt style; do not reset the user\'s Kvantum configuration.\n\n' + text[end:]
    start, end = text.index('  # Fallback for GTK3/GTK4 apps'), text.index('  local libadwaita_tool', text.index('  # Fallback for GTK3/GTK4 apps'))
    text = text[:start] + '''  # Update only reviewed appearance keys; retain application modules and user data.
  /usr/lib/xodus/apply-user-toolkit-mode --mode "$mode"
  if have gsettings; then
    gsettings set org.gnome.desktop.interface font-name "Noto Sans 10" || true
  fi
  # Automatic timers run while Settings is closed; keep the Dock skin in sync.
  local dock_skin="Xodus Dark"
  [ "$mode" = "light" ] && dock_skin="Xodus Light"
  local dock_script="var ps=panels(); for(var i=0;i<ps.length;i++){var ws=ps[i].widgets(); for(var j=0;j<ws.length;j++){if(ws[j].type==='PearDock'){ws[j].currentConfigGroup=['General'];ws[j].writeConfig('skinName','$dock_skin');ws[j].reloadConfig();}}}"
  if have qdbus6; then
    qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$dock_script" >/dev/null 2>&1 || true
  elif have qdbus; then
    qdbus org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$dock_script" >/dev/null 2>&1 || true
  fi

''' + text[end:]
    return text.encode()

#!/usr/bin/env python3
"""Capture reviewed live identity bytes and transfer them into a fresh target.

No partitions, mounts, accounts, drivers, services or bootloader commands are
created by this helper. Installer hooks run the existing boot configuration
commands after the boot files have been staged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import subprocess

MANIFEST = 'usr/lib/xodus/identity-payload.json'
SKEL = (
    '.config/autostart/pearos-notch.desktop',
    '.config/autostart/welcome.desktop',
    '.config/autostart/xodus-welcome.desktop',
    '.config/filer-topbar-appletsrc',
    '.config/gtk-3.0/colors.css',
    '.config/gtk-3.0/gtk.css',
    '.config/gtk-3.0/settings.ini',
    '.config/gtk-4.0/colors.css',
    '.config/gtk-4.0/gtk.css',
    '.config/gtk-4.0/settings.ini',
    '.config/kcminputrc',
    '.config/kdeglobals',
    '.config/kscreenlockerrc',
    '.config/ksplashrc',
    '.config/kwinrc',
    '.config/plasma-org.kde.plasma.desktop-appletsrc',
    '.config/plasma-org.kde.plasma.desktop-appletsrc.bak',
    '.config/plasmarc',
    '.gtkrc-2.0',
    '.local/share/konsole/Fancy Blur.colorscheme',
    '.local/share/konsole/pearOS Fancy.profile',
    '.local/share/konsole/pearOS Normal.profile',
    '.themes/pearOS-Dark/index.theme',
    '.themes/pearOS-Light/index.theme',
)
FIXED = [
    'usr/share/wallpapers/Xodus/xodus-wallpaper.png',
    'usr/share/pixmaps/xodus-app-icon.png',
    'usr/lib/xodus/xodus-welcome', 'usr/lib/xodus/xodus-settings',
    'usr/lib/xodus/xodus-restore-user-identity', 'usr/lib/xodus/xodus-identity-payload',
    'usr/lib/xodus/settings-source.json', 'usr/lib/xodus/release-source.json',
    'usr/lib/xodus/upstream-os-release', 'usr/lib/os-release', 'etc/arch-release',
    'usr/bin/systemsettings1', 'usr/bin/system-overview',
    'usr/share/applications/welcome.desktop',
    'usr/share/applications/xodus-welcome.desktop',
    'usr/share/applications/pearos-systemsettings.desktop',
    'usr/share/applications/pearos-notch.desktop',
    'usr/share/licenses/xodus-shell/LICENSE',
    'usr/share/licenses/xodus-settings/NOTICE',
    'usr/share/licenses/xodus-settings/upstream-license.txt',
    'usr/share/color-schemes/Xodus.colors',
    'etc/sddm.conf.d/20-xodus-theme.conf',
    'usr/share/sounds/pearOS-sounds/index.theme',
    'usr/share/plasma/plasmoids/xyz.pearos.pearmenu/metadata.json',
    'usr/share/plasma/plasmoids/xyz.pearos.pearmenu/contents/config/main.xml',
    'usr/share/plasma/plasmoids/xyz.pearos.pearmenu/contents/ui/MainMenuButton.qml',
    'usr/share/plasma/plasmoids/PearDock/contents/ui/integrations/PearFinder.qml',
    'usr/share/plasma/plasmoids/PearDock/contents/ui/integrations/PearLauncher.qml',
    'usr/share/plasma/plasmoids/PearAppTitle/contents/config/main.xml',
    'usr/share/plasma/plasmoids/PearAppTitle/contents/ui/config/ConfigAppearance.qml',
    'usr/share/plasma/plasmoids/PearLauncher/contents/config/main.xml',
    'usr/share/plasma/plasmoids/PearLauncher/contents/ui/main.qml',
]
for widget in ('PearAppTitle', 'PearClock', 'PearCalendar', 'PearControlCentre',
               'PearFinder', 'PearFolderArc', 'PearLauncher', 'PearPrivacy',
               'PearTaskManager', 'PearTrash', 'PearWeather', 'PearDock'):
    FIXED.append(f'usr/share/plasma/plasmoids/{widget}/metadata.json')
for variant in ('pearOS', 'pearOS-dark'):
    for name in ('Main.qml', 'theme.conf', 'theme.conf.user', 'metadata.desktop'):
        FIXED.append(f'usr/share/sddm/themes/{variant}/{name}')
    for name in ('metadata.json', 'contents/splash/Splash.qml'):
        FIXED.append(f'usr/share/plasma/look-and-feel/{variant}/{name}')
    for name in ('metadata.json', 'metadata.desktop'):
        FIXED.append(f'usr/share/plasma/desktoptheme/{variant}/{name}')
    FIXED += [f'usr/share/color-schemes/{variant}.colors',
              f'usr/share/aurorae/themes/{variant}/metadata.desktop']
for name in ('Main.qml', 'metadata.desktop', 'theme.conf', 'LICENSE'):
    FIXED.append(f'usr/share/sddm/themes/Xodus/{name}')
COMPONENT_FILES = (
    'usr/lib/xodus/apply-user-toolkit-mode',
    'usr/lib/xodus/desktop-identity.json',
    'usr/lib/xodus/dock-source.json',
    'usr/lib/xodus/toolkit-source.json',
    'usr/share/color-schemes/Xodus Light.colors',
    'usr/share/extras/system-settings/themeswitcher/colors.json',
    'usr/share/extras/system-settings/themeswitcher/colors/azul.ini',
    'usr/share/extras/system-settings/themeswitcher/colors/blue.ini',
    'usr/share/extras/system-settings/themeswitcher/colors/dark-purple.ini',
    'usr/share/extras/system-settings/themeswitcher/colors/green.ini',
    'usr/share/extras/system-settings/themeswitcher/colors/grey.ini',
    'usr/share/extras/system-settings/themeswitcher/colors/lila.ini',
    'usr/share/extras/system-settings/themeswitcher/colors/magenta.ini',
    'usr/share/extras/system-settings/themeswitcher/colors/orange.ini',
    'usr/share/extras/system-settings/themeswitcher/colors/purple.ini',
    'usr/share/extras/system-settings/themeswitcher/colors/yellow.ini',
    'usr/share/extras/system-settings/themeswitcher/config.json',
    'usr/share/extras/system-settings/themeswitcher/config.py',
    'usr/share/extras/system-settings/themeswitcher/kde-theme-switch.sh',
    'usr/share/extras/system-settings/themeswitcher/libadwaita',
    'usr/share/konsole/Xodus Dark.colorscheme',
    'usr/share/konsole/Xodus Glass.colorscheme',
    'usr/share/konsole/Xodus Light Glass.colorscheme',
    'usr/share/konsole/Xodus Light.colorscheme',
    'usr/share/licenses/xodus-desktop/NOTICE',
    'usr/share/licenses/xodus-dock/NOTICE',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Light/Config.qml',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Light/bg.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Light/bgl.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Light/bgr.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Light/bgt.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Light/readme',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Light/tasks.svgz',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Night/Config.qml',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Night/bg.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Night/bgl.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Night/bgr.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Night/bgt.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Night/readme',
    'usr/share/licenses/xodus-dock/upstream-skins/Big Sur Night/tasks.svgz',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe Dark/Config.qml',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe Dark/bg.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe Dark/bgl.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe Dark/bgr.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe Dark/bgt.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe Dark/tasks.svgz',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe/Config.qml',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe/bg.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe/bgl.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe/bgr.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe/bgt.png',
    'usr/share/licenses/xodus-dock/upstream-skins/Tahoe/tasks.svgz',
    'usr/share/licenses/xodus-dock/upstream-skins/readme',
    'usr/share/licenses/xodus-toolkit/LICENSE',
    'usr/share/licenses/xodus-toolkit/NOTICE',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.config/gtk-3.0/colors.css',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.config/gtk-3.0/gtk.css',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.config/gtk-3.0/settings.ini',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.config/gtk-4.0/colors.css',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.config/gtk-4.0/gtk.css',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.config/gtk-4.0/settings.ini',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.gtkrc-2.0',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.local/share/konsole/Fancy Blur.colorscheme',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.local/share/konsole/pearOS Fancy.profile',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.local/share/konsole/pearOS Normal.profile',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.themes/pearOS-Dark/index.theme',
    'usr/share/licenses/xodus-toolkit/upstream/etc/skel/.themes/pearOS-Light/index.theme',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.config/gtk-3.0/colors.css',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.config/gtk-3.0/gtk.css',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.config/gtk-3.0/settings.ini',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.config/gtk-4.0/colors.css',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.config/gtk-4.0/gtk.css',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.config/gtk-4.0/settings.ini',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.gtkrc-2.0',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.local/share/konsole/Fancy Blur.colorscheme',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.local/share/konsole/pearOS Fancy.profile',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.local/share/konsole/pearOS Normal.profile',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.themes/pearOS-Dark/index.theme',
    'usr/share/licenses/xodus-toolkit/upstream/home/liveuser/.themes/pearOS-Light/index.theme',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors.json',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/azul.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/blue.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/dark-purple.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/green.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/grey.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/lila.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/magenta.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/orange.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/purple.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/colors/yellow.ini',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/config.json',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/config.py',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/kde-theme-switch.sh',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/extras/system-settings/themeswitcher/libadwaita',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/themes/pearOS-dark/index.theme',
    'usr/share/licenses/xodus-toolkit/upstream/usr/share/themes/pearOS/index.theme',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/assets/Ko-Fi.png',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/assets/Paypal.png',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/assets/control.png',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/assets/music.png',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/assets/music.svg',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/assets/xodus-controls.svg',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/config/config.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/config/main.xml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/locale/de/LC_MESSAGES/plasma_applet_KdeControlStation.mo',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/locale/es/LC_MESSAGES/plasma_applet_KdeControlStation.mo',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/locale/fr/LC_MESSAGES/plasma_applet_KdeControlStation.mo',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/locale/ko/LC_MESSAGES/plasma_applet_KdeControlStation.mo',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/locale/nl/LC_MESSAGES/plasma_applet_KdeControlStation.mo',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/locale/pl/LC_MESSAGES/plasma_applet_KdeControlStation.mo',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/locale/pt_BR/LC_MESSAGES/plasma_applet_KdeControlStation.mo',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/locale/uk/LC_MESSAGES/plasma_applet_KdeControlStation.mo',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/CompactRepresentation.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/FullRepresentation.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/Battery.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/BluetoothBtn.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/BrightnessSlider.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/ColorSchemeSwitcher.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/CommandRun.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/DndButton.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/KDEConnect.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/MediaPlayer.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/Network.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/NetworkBtn.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/NightLight.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/RedShift.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/ScreenshotBtn.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/SystemActions.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/UserAvatar.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/components/Volume.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/config/components/ColorChooser.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/config/configAppearance.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/config/configColorscheme.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/config/configScreenshot.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/config/configSupport.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/icons/feather/dark-mode.svg',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/icons/feather/notifications-off.svg',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/icons/feather/notifications-on.svg',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/icons/feather/pwr.svg',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/js/brightness.js',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/js/colorType.js',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/js/funcs.js',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/js/helpers.js',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/ControlCenter.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/Custom.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/Default.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/Flat.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/Tahoe.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/Xodus.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/components/ControlCenter/LeftColumn.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/components/ControlCenter/RightColumn.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/components/Custom/ActionMenu.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/components/Custom/ContextMenuItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/components/Custom/ContextMenuTemplate.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/components/Custom/Footer.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/components/Custom/Model.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/components/Default/SectionQuickToggleButtons.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/layouts/components/Default/SectionScreenControls.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/lib/Card.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/lib/CardButton.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/lib/Icon.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/lib/LongButton.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/lib/Slider.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/main.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/BatteryPage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/BluetoothPage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/BrightnessControlPage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/MediaPlayerPage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/NetworkPage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/NightLightPage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/PageTemplate.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/SystemSessionActionsPage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/VolumePage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/battery/BatteryItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/battery/InhibitionHint.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/battery/MainView.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/battery/PowerManagementItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/battery/PowerProfileItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/bluetooth/DeviceItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/bluetooth/Header.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/bluetooth/MediaPlayerItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/brightness/BrightnessItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/brightness/KeyboardColorItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/mediaPlayer/AlbumArtStackView.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/mediaPlayer/ExpandedRepresentation.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/network/ConnectionItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/network/ConnectionListPage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/network/DetailsText.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/network/ListItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/network/PasswordField.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/network/ShareNetworkQrCodePage.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/network/Toolbar.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/network/TrafficMonitor.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/volume/DeviceListItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/volume/HorizontalStackView.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/volume/ListItemBase.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/volume/SmallToolButton.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/volume/StreamListItem.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/pages/components/volume/VolumeSlider.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/xodus/ActionButton.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/xodus/ControlPanel.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/xodus/ControlTile.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/xodus/Controller.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/xodus/Glyph.qml',
    'usr/share/plasma/plasmoids/PearControlCentre/contents/ui/xodus/LevelControl.qml',
    'usr/share/plasma/plasmoids/PearDock/contents/config/main.xml',
    'usr/share/plasma/plasmoids/PearDock/contents/skins/Xodus Dark/Config.qml',
    'usr/share/plasma/plasmoids/PearDock/contents/skins/Xodus Dark/frame.png',
    'usr/share/plasma/plasmoids/PearDock/contents/skins/Xodus Dark/frame.svg',
    'usr/share/plasma/plasmoids/PearDock/contents/skins/Xodus Dark/tasks.svg',
    'usr/share/plasma/plasmoids/PearDock/contents/skins/Xodus Light/Config.qml',
    'usr/share/plasma/plasmoids/PearDock/contents/skins/Xodus Light/frame.png',
    'usr/share/plasma/plasmoids/PearDock/contents/skins/Xodus Light/frame.svg',
    'usr/share/plasma/plasmoids/PearDock/contents/skins/Xodus Light/tasks.svg',
    'usr/share/plasma/plasmoids/PearDock/contents/ui/ConfigAppearance.qml',
    'usr/share/plasma/plasmoids/PearDock/contents/ui/XodusSkinSelector.qml',
    'usr/share/plasma/plasmoids/PearDock/contents/ui/main.qml',
    'usr/share/themes/Xodus-Dark/gtk-2.0/gtkrc',
    'usr/share/themes/Xodus-Dark/gtk-3.0/gtk-dark.css',
    'usr/share/themes/Xodus-Dark/gtk-3.0/gtk.css',
    'usr/share/themes/Xodus-Dark/gtk-4.0/gtk-dark.css',
    'usr/share/themes/Xodus-Dark/gtk-4.0/gtk.css',
    'usr/share/themes/Xodus-Dark/index.theme',
    'usr/share/themes/Xodus-Light/gtk-2.0/gtkrc',
    'usr/share/themes/Xodus-Light/gtk-3.0/gtk-dark.css',
    'usr/share/themes/Xodus-Light/gtk-3.0/gtk.css',
    'usr/share/themes/Xodus-Light/gtk-4.0/gtk-dark.css',
    'usr/share/themes/Xodus-Light/gtk-4.0/gtk.css',
    'usr/share/themes/Xodus-Light/index.theme',
    'usr/share/themes/pearOS-dark/index.theme',
    'usr/share/themes/pearOS/index.theme',
    'usr/share/xodus/identity/control-center.json',
)
COMPONENT_EXECUTABLES = (
    'usr/lib/xodus/apply-user-toolkit-mode',
    'usr/share/extras/system-settings/themeswitcher/config.py',
    'usr/share/extras/system-settings/themeswitcher/kde-theme-switch.sh',
    'usr/share/extras/system-settings/themeswitcher/libadwaita',
)
FIXED += COMPONENT_FILES
FIXED += ['etc/skel/' + relative for relative in SKEL]
BOOT_TREES = ('usr/share/plymouth/themes/xodus', 'usr/share/grub/themes/Xodus')
BOOT_REQUIRED = {
    'usr/share/plymouth/themes/xodus/xodus.plymouth',
    'usr/share/plymouth/themes/xodus/xodus.script',
    'usr/share/grub/themes/Xodus/theme.txt',
    'usr/share/grub/themes/Xodus/background.png',
    *(f'usr/share/plymouth/themes/xodus/frame-{index:03d}.png' for index in range(241)),
    *(f'usr/share/grub/themes/Xodus/{name}.pf2' for name in (
        'Poppins-14', 'Poppins-16', 'Poppins-18', 'Poppins-20', 'Poppins-48',
        'terminus-12', 'terminus-14', 'terminus-16')),
}
DOCK_SKINS = 'usr/share/plasma/plasmoids/PearDock/contents/skins'
DOCK_UPSTREAM_SKIN_HASHES = {
    'Big Sur Light/Config.qml': 'e0b16097719b390c552ff1738ee49d2caa6927136d3c11ed792954a3110ddd0d',
    'Big Sur Light/bg.png': 'b7192daa81c12ffb6668859649018d90e1e36bab14a683538ae251dd2a95c054',
    'Big Sur Light/bgl.png': '87ba06f1464779bc59e1fcc17b4b885b5e894fed78b3163084f8056ac6618715',
    'Big Sur Light/bgr.png': '7226b6e3b6dfd23679a774ff735d993f68703efee67c475ec3047f0d393fb5e9',
    'Big Sur Light/bgt.png': '657865b8c97d8a5038dcbbaed898a892e26a0bc6e6e58bcf4837af735c069e40',
    'Big Sur Light/readme': '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b',
    'Big Sur Light/tasks.svgz': '5894378587d47d6f24ee672fc9e110f55bd94d3e7299cadb00c9fd67cb6ae672',
    'Big Sur Night/Config.qml': '098b9653b6033d6b3735622f96de508118e1467f7a2c7e3ac2ebdbe8c76a0ad8',
    'Big Sur Night/bg.png': 'fe6b7a5bb86c36bda71bc888efc5ef070cc641a84ad0046660591dcaea4fbc08',
    'Big Sur Night/bgl.png': '5dcb9585569be6ca815e33fbb07fb1a61956bce131ea4e7c006d635c11413c1d',
    'Big Sur Night/bgr.png': '8baa4186bf63454a0ab60edde33f8534cd9bc555b1603f2baf7035d0593c9048',
    'Big Sur Night/bgt.png': '568f953cce19b66c8abb46a40af3c4f699733032a510d22399cd5bbab62f03de',
    'Big Sur Night/readme': '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b',
    'Big Sur Night/tasks.svgz': '8bfe0529d87b5d1b84c153318703aab24d229e3830b61aeb35932ccdb4335bbd',
    'Tahoe Dark/Config.qml': 'dbbb6c3322d003024b864abef0093c4a747e1ea6866af54d467f0bb63d987b48',
    'Tahoe Dark/bg.png': '030336241dc3c9c939882118f6d4c969211f16cbe87889abbaf6448b78fa57e6',
    'Tahoe Dark/bgl.png': '64964c9dedbd9ce19571ab431b0c23cd6dfd9fd2742d305ee85c88c86bf3ee18',
    'Tahoe Dark/bgr.png': '5b24a35ea91df3d782a4785d5bb210aa0c1f06f87b7887e5ee8e38edb40645f6',
    'Tahoe Dark/bgt.png': '9e6a62f4a115e6bdf46def2cfa0e3918e38e96e4c30e2dec4ef8ea369a24d348',
    'Tahoe Dark/tasks.svgz': '8bfe0529d87b5d1b84c153318703aab24d229e3830b61aeb35932ccdb4335bbd',
    'Tahoe/Config.qml': '5bb90ec0d500bb149ac59e03de100eba33d43f94ade835e5fb1a8f04192ea269',
    'Tahoe/bg.png': 'e2fdf70e637914c4ef7de2544d8129d70155d096e3390da5cb6365cbc9c1ec62',
    'Tahoe/bgl.png': 'c1c5e30a6d4ec0430e893dcff64ac4a28e2f24594611385226977ed03b327803',
    'Tahoe/bgr.png': 'a5064283c8ec94c1582cf9c3a3a63118d07777d6b8fe0f640705c40818e32d6b',
    'Tahoe/bgt.png': '9357bf654ebceb8ac67ebc92366b587855b93864cddce17f1baeefcf101dcd08',
    'Tahoe/tasks.svgz': '5894378587d47d6f24ee672fc9e110f55bd94d3e7299cadb00c9fd67cb6ae672',
    'readme': '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b',
}
RUNTIME_DEPENDENCIES = (
    'usr/lib/qt6/plugins/styles/breeze6.so',
    'usr/share/icons/breeze-dark/index.theme',
    'usr/share/icons/breeze/index.theme',
    'usr/share/icons/breeze_cursors/index.theme',
    'usr/share/plasma/desktoptheme/default/metadata.json',
    'usr/share/plasma/look-and-feel/org.kde.breezedark.desktop/metadata.json',
)
DECORATION_PATHS = (
    'usr/lib/qt6/plugins/org.kde.kdecoration2/org.kde.breeze.so',
    'usr/lib/qt6/plugins/org.kde.kdecoration3/org.kde.breeze.so',
)
OPTIONAL = ('usr/lib/xodus/upstream-etc-os-release',)
SHA = re.compile(r'^[0-9a-f]{40}$')


def fail(message):
    raise ValueError('Xodus installed identity: ' + message)


def safe(root: Path, relative: str, required=False):
    path_parts = Path(relative).parts
    if not relative or relative.startswith('/') or '..' in path_parts or '.' in path_parts:
        fail('unsafe relative path: ' + relative)
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            fail('symlink in identity path: ' + relative)
        if candidate != path and candidate.exists() and not candidate.is_dir():
            fail('non-directory identity parent: ' + relative)
    if root not in path.resolve().parents:
        fail('identity path escapes root: ' + relative)
    if path.exists() and not path.is_file():
        fail('identity destination is not regular: ' + relative)
    if path.is_file() and path.stat().st_nlink != 1:
        fail('hardlink in identity path: ' + relative)
    if required and not path.is_file():
        fail('missing identity file: ' + relative)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_commit(root):
    text = safe(root, 'usr/lib/xodus/build-info', True).read_text()
    values = re.findall(r'^XODUS_SOURCE_COMMIT=([0-9a-f]{40})$', text, re.M)
    if len(values) != 1:
        fail('live image lacks one exact Xodus source commit')
    return values[0]


def inventory(root):
    # The package may include many other files. Only this closed inventory is
    # transferred; an extra executable or arbitrary theme file is never admitted.
    files = set(FIXED) | BOOT_REQUIRED
    for relative in BOOT_TREES:
        directory = root / relative
        if directory.is_symlink() or not directory.is_dir():
            fail('missing or unsafe boot theme tree: ' + relative)
    files.update(relative for relative in OPTIONAL if safe(root, relative).exists())
    return sorted(files)


def file_mode(relative):
    return '0755' if relative.startswith('usr/bin/') or relative in (
        'usr/lib/xodus/xodus-welcome', 'usr/lib/xodus/xodus-settings',
        'usr/lib/xodus/xodus-restore-user-identity', 'usr/lib/xodus/xodus-identity-payload') or relative in COMPONENT_EXECUTABLES else '0644'


def verify_brand(root):
    for name in ('xodus-welcome', 'xodus-settings'):
        path = safe(root, 'usr/lib/xodus/' + name, True)
        if path.read_bytes()[:4] != b'\x7fELF' or not os.access(path, os.X_OK):
            fail('missing executable compiled app: ' + name)
    checks = {
        'usr/share/applications/xodus-welcome.desktop': 'Name=Xodus Welcome',
        'usr/share/applications/pearos-systemsettings.desktop': 'Name=Xodus Settings',
        'etc/sddm.conf.d/20-xodus-theme.conf': 'Current=Xodus',
        'etc/skel/.config/kdeglobals': 'ColorScheme=Xodus',
        'usr/share/color-schemes/Xodus.colors': 'Name=Xodus',
        'usr/share/grub/themes/Xodus/theme.txt': 'Xodus',
        'usr/share/plymouth/themes/xodus/xodus.plymouth': 'Name=Xodus',
        'usr/lib/os-release': 'ID=xodus',
    }
    for relative, marker in checks.items():
        if marker not in safe(root, relative, True).read_text():
            fail('live identity is not applied: ' + relative)


def capture(root):
    if root.is_symlink() or not root.is_dir():
        fail('capture requires a real staged live root')
    root = root.resolve(strict=True)
    if root == Path('/'):
        fail('capture requires a staged live root')
    commit = source_commit(root)
    files = inventory(root)
    verify_brand(root)
    entries = []
    for relative in files:
        path = safe(root, relative, True)
        mode = file_mode(relative)
        if mode == '0755' and not os.access(path, os.X_OK):
            fail('required executable mode is missing: ' + relative)
        entries.append({'path': relative, 'sha256': digest(path),
                        'mode': mode})
    manifest = {'schema': 1, 'source_commit': commit, 'files': entries}
    output = safe(root, MANIFEST)
    if output.exists():
        fail('live identity manifest already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    return manifest


def read_manifest(source, expected_source):
    if not SHA.fullmatch(expected_source) or source_commit(source) != expected_source:
        fail('live image source does not match the qualified installer')
    document = json.loads(safe(source, MANIFEST, True).read_text())
    if set(document) != {'schema', 'source_commit', 'files'} or document['schema'] != 1:
        fail('invalid identity manifest schema')
    if document['source_commit'] != expected_source:
        fail('identity manifest source does not match the qualified installer')
    files = document['files']
    if not isinstance(files, list) or not files:
        fail('empty identity manifest')
    paths = []
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {'path', 'sha256', 'mode'}:
            fail('invalid identity manifest entry')
        relative = entry['path']
        if not isinstance(relative, str) or relative not in set(FIXED) | BOOT_REQUIRED | set(OPTIONAL):
            fail('identity manifest attempts an unreviewed path')
        paths.append(relative)
        if entry['mode'] != file_mode(relative) or not isinstance(entry['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
            fail('invalid identity hash or mode')
        if digest(safe(source, relative, True)) != entry['sha256']:
            fail('live identity payload hash changed: ' + relative)
    if paths != sorted(set(paths)) or set(paths) != set(inventory(source)):
        fail('identity manifest file inventory changed')
    verify_brand(source)
    return document


def grub_defaults(target):
    path = safe(target, 'etc/default/grub', True)
    lines = path.read_text().splitlines()
    for key, value in (('GRUB_THEME', '"/usr/share/grub/themes/Xodus/theme.txt"'),
                       ('GRUB_DISTRIBUTOR', '"Xodus"')):
        positions = [i for i, line in enumerate(lines) if re.match(r'^\s*' + key + r'\s*=', line)]
        if len(positions) > 1:
            fail('duplicate installed GRUB setting: ' + key)
        if positions:
            lines[positions[0]] = key + '=' + value
        else:
            lines.append(key + '=' + value)
    return path, '\n'.join(lines) + '\n'


def initramfs_hooks(target):
    path = safe(target, 'etc/mkinitcpio.conf', True)
    text = path.read_text()
    matches = list(re.finditer(r'^HOOKS=\(([^\n]*)\)$', text, re.M))
    if len(matches) != 1:
        fail('installed initramfs must contain one reviewed HOOKS array')
    match = matches[0]
    hooks = match.group(1).split()
    if not hooks or any(not re.fullmatch(r'[a-zA-Z0-9_-]+', hook) for hook in hooks):
        fail('unreviewed installed initramfs hook syntax')
    if 'systemd' in hooks or 'sd-plymouth' in hooks:
        fail('installed systemd initramfs requires a separately reviewed Plymouth hook')
    if 'plymouth' not in hooks:
        # Keep all target hooks in their existing order. Plymouth runs after
        # display setup and before any encrypt/password prompt hook.
        position = hooks.index('kms') + 1 if 'kms' in hooks else hooks.index('udev') + 1 if 'udev' in hooks else 1
        hooks.insert(position, 'plymouth')
    if hooks.count('plymouth') != 1:
        fail('duplicate installed Plymouth hook')
    return path, text[:match.start()] + 'HOOKS=(' + ' '.join(hooks) + ')' + text[match.end():]


def release_link(target):
    path = target / 'etc/os-release'
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir() or target not in parent.resolve().parents:
        fail('unsafe installed OS release parent')
    if path.is_symlink():
        if os.readlink(path) not in ('../usr/lib/os-release', '/usr/lib/os-release'):
            fail('unreviewed installed OS release symlink')
        return path, 'link'
    if path.exists() and not path.is_file():
        fail('invalid installed OS release file')
    return path, 'regular' if path.exists() else 'new-link'


def user_homes(target):
    accounts = safe(target, 'etc/passwd', True).read_text().splitlines()
    result = []
    for row in accounts:
        fields = row.split(':')
        if len(fields) != 7:
            fail('invalid target account record')
        uid, gid = int(fields[2]), int(fields[3])
        home = fields[5]
        if not 1000 <= uid < 60000 or not home.startswith('/home/'):
            continue
        relative = home.lstrip('/')
        directory = target / relative
        if directory.is_symlink() or not directory.is_dir() or target not in directory.resolve().parents:
            fail('unsafe target user home: ' + home)
        result.append((relative, uid, gid))
    return result


def target_boundary(source, target):
    if target == Path('/') or source == target:
        fail('target must be a separate installation root')
    if source == Path('/'):
        # The pinned setup mounts its selected target at exactly /mnt. Source
        # paths come only from the closed /usr and /etc graphical allowlist.
        if target != Path('/mnt'):
            fail('real live source may transfer only into the pinned /mnt target')
    elif source in target.parents or target in source.parents:
        fail('fixture target must be independent of the staged live source')


def sddm_selections(target):
    directory = target / 'etc/sddm.conf.d'
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        fail('unsafe installed SDDM configuration directory')
    updates = []
    paths = [target / 'etc/sddm.conf', *directory.glob('*.conf')]
    for path in paths:
        relative = path.relative_to(target).as_posix()
        if relative == 'etc/sddm.conf.d/20-xodus-theme.conf':
            continue  # The full transfer replaces this reviewed selection.
        if not path.exists() and not path.is_symlink():
            continue
        path = safe(target, relative, True)
        section = None
        output = []
        for line in path.read_text().splitlines(keepends=True):
            heading = re.fullmatch(r'\s*\[([^]\n]+)\]\s*', line.strip())
            if heading:
                section = heading.group(1)
            if re.match(r'^\s*Current\s*=', line):
                if section != 'Theme':
                    fail('unreviewed installed SDDM Current setting: ' + relative)
                continue
            output.append(line)
        contents = ''.join(output).encode()
        if contents != path.read_bytes():
            updates.append((path, contents, stat.S_IMODE(path.stat().st_mode), None))
    return updates


def safe_directory(root, relative):
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_dir()):
            fail('unsafe installed appearance directory: ' + relative)
    if root not in path.resolve().parents:
        fail('appearance directory escapes target: ' + relative)
    return path


def guest_executable(root, relative):
    """Resolve the qdbus package link inside the guest, never against the host."""
    visited = set()
    for _ in range(16):
        if relative in visited:
            fail('cyclic installed qdbus6 executable link')
        visited.add(relative)
        path = root / relative
        safe_directory(root, path.parent.relative_to(root).as_posix())
        if not path.is_symlink():
            if relative not in ('usr/bin/qdbus6', 'usr/lib/qt6/bin/qdbus'):
                fail('installed qdbus6 executable link has an unreviewed destination')
            path = safe(root, relative, True)
            if not os.access(path, os.X_OK):
                fail('installed qdbus6 executable mode is missing')
            return path
        link = os.readlink(path)
        resolved = posixpath.normpath(link if link.startswith('/') else '/' +
                                     posixpath.join(posixpath.dirname(relative), link))
        if not resolved.startswith('/') or resolved == '/' or resolved.startswith('/../'):
            fail('installed qdbus6 executable link escapes guest')
        relative = resolved.lstrip('/')
    fail('installed qdbus6 executable link is too deep')


def appearance_dependencies(target):
    for relative in RUNTIME_DEPENDENCIES:
        safe(target, relative, True)
    if not any(safe(target, relative).is_file() for relative in DECORATION_PATHS):
        fail('installed Breeze window decoration plugin is missing')
    guest_executable(target, 'usr/bin/qdbus6')


def old_dock_removals(source, target):
    """Preflight the closed reviewed skin tree before any target mutation."""
    for relative, expected in DOCK_UPSTREAM_SKIN_HASHES.items():
        original = 'usr/share/licenses/xodus-dock/upstream-skins/' + relative
        if digest(safe(source, original, True)) != expected:
            fail('reviewed upstream Dock skin archive changed: ' + relative)
    directory = safe_directory(target, DOCK_SKINS)
    if not directory.exists():
        return [], []
    new_files = {relative.removeprefix(DOCK_SKINS + '/') for relative in FIXED
                 if relative.startswith(DOCK_SKINS + '/')}
    allowed_files = new_files | set(DOCK_UPSTREAM_SKIN_HASHES)
    allowed_directories = {parent.as_posix() for relative in allowed_files
                           for parent in Path(relative).parents if parent.as_posix() != '.'}
    observed_old = set()
    for path in directory.rglob('*'):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            fail('symlink in installed Dock skin tree: ' + relative)
        if path.is_dir():
            if relative not in allowed_directories:
                fail('unreviewed installed Dock skin directory: ' + relative)
            safe_directory(target, path.relative_to(target).as_posix())
        elif path.is_file():
            if relative not in allowed_files:
                fail('unreviewed installed Dock skin file: ' + relative)
            checked = safe(target, path.relative_to(target).as_posix(), True)
            if relative in DOCK_UPSTREAM_SKIN_HASHES:
                observed_old.add(relative)
                if digest(checked) != DOCK_UPSTREAM_SKIN_HASHES[relative]:
                    fail('installed upstream Dock skin changed: ' + relative)
        else:
            fail('nonregular installed Dock skin entry: ' + relative)
    if observed_old and observed_old != set(DOCK_UPSTREAM_SKIN_HASHES):
        fail('installed upstream Dock skin inventory is incomplete')
    # Empty inherited folders are also rejected: a reviewed package has all 27
    # files, while a completed identity transfer has none of those folders.
    old_directories = {parent.as_posix() for relative in DOCK_UPSTREAM_SKIN_HASHES
                       for parent in Path(relative).parents if parent.as_posix() != '.'}
    if not observed_old and any((directory / relative).exists() for relative in old_directories):
        fail('installed upstream Dock skin inventory is incomplete')
    files = [safe(target, DOCK_SKINS + '/' + relative, True) for relative in sorted(observed_old)]
    directories = [safe_directory(target, DOCK_SKINS + '/' + relative)
                   for relative in sorted(old_directories, key=lambda value: (-len(Path(value).parts), value))
                   if (directory / relative).exists()]
    return files, directories


def runtime_check(target):
    for name, libs, style, arguments in (
        ('xodus-welcome', ('libQt5Widgets.so.5', 'libQt5Gui.so.5', 'libQt5Core.so.5'),
         'QT_STYLE_OVERRIDE=Fusion', ['--self-test']),
        ('xodus-settings', ('libQt6Core.so.6', 'libQt6Gui.so.6', 'libQt6Quick.so.6', 'libQt6Qml.so.6'),
         'QT_QUICK_CONTROLS_STYLE=Basic', ['--self-test', '--about']),
    ):
        binary = '/usr/lib/xodus/' + name
        result = subprocess.run(['arch-chroot', str(target), '/usr/bin/ldd', binary],
                                capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        if result.returncode or 'not found' in output or any(lib not in output for lib in libs):
            fail('installed app ABI check failed: ' + name)
        result = subprocess.run(['arch-chroot', str(target), '/usr/bin/env',
                                 'LD_BIND_NOW=1', 'QT_QPA_PLATFORM=offscreen',
                                 'QT_QUICK_BACKEND=software', style, binary, *arguments],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            fail('installed app render check failed: ' + name)


def install(source, target, expected_source, phase='full'):
    if source.is_symlink() or target.is_symlink() or not source.is_dir() or not target.is_dir():
        fail('source and target must be real directories')
    source, target = source.resolve(strict=True), target.resolve(strict=True)
    target_boundary(source, target)
    document = read_manifest(source, expected_source)
    entries = [entry for entry in document['files'] if phase == 'full' or any(
        entry['path'].startswith(prefix + '/') for prefix in BOOT_TREES)]
    updates = [(safe(target, entry['path']), safe(source, entry['path'], True).read_bytes(),
                int(entry['mode'], 8), None) for entry in entries]
    grub, contents = grub_defaults(target)
    updates.append((grub, contents.encode(), 0o644, None))
    if phase == 'boot':
        hooks, contents = initramfs_hooks(target)
        updates.append((hooks, contents.encode(), 0o644, None))
    release = None
    removals, removal_directories = [], []
    receipt = None
    if phase == 'full':
        appearance_dependencies(target)
        removals, removal_directories = old_dock_removals(source, target)
        receipt = safe(target, 'usr/lib/xodus/installed-identity.json')
        updates.extend(sddm_selections(target))
        release, release_kind = release_link(target)
        if release_kind == 'regular':
            updates.append((release, safe(source, 'usr/lib/os-release', True).read_bytes(), 0o644, None))
        for home, uid, gid in user_homes(target):
            for relative in SKEL:
                updates.append((safe(target, home + '/' + relative),
                                safe(source, 'etc/skel/' + relative, True).read_bytes(),
                                0o644, (uid, gid)))
    # All source checks and destination path checks finish before transfer.
    # ABI checks necessarily follow staging, and abort the installer on failure.
    for path in removals:
        path.unlink()
    for directory in removal_directories:
        directory.rmdir()
    for path, contents, mode, ownership in updates:
        missing = []
        parent = path.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        path.parent.mkdir(parents=True, exist_ok=True)
        if ownership:
            for parent in missing:
                os.chown(parent, *ownership)
        path.write_bytes(contents)
        path.chmod(mode)
        if ownership:
            os.chown(path, *ownership)
    if phase == 'full':
        if release_kind == 'new-link':
            release.symlink_to('../usr/lib/os-release')
        runtime_check(target)
        receipt.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Installed Xodus identity phase={phase} files={len(updates)} source={expected_source}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    cap = subparsers.add_parser('capture')
    cap.add_argument('root', type=Path)
    transfer = subparsers.add_parser('install')
    transfer.add_argument('--source-root', type=Path, default=Path('/'))
    transfer.add_argument('--target-root', type=Path, required=True)
    transfer.add_argument('--expected-source', required=True)
    transfer.add_argument('--phase', choices=('boot', 'full'), default='full')
    verify = subparsers.add_parser('verify')
    verify.add_argument('--source-root', type=Path, default=Path('/'))
    verify.add_argument('--expected-source', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'capture':
            manifest = capture(args.root)
            print(f'Captured Xodus identity source={manifest["source_commit"]} files={len(manifest["files"])}')
        elif args.command == 'install':
            install(args.source_root, args.target_root, args.expected_source, args.phase)
        else:
            read_manifest(args.source_root.resolve(strict=True), args.expected_source)
            print('Verified qualified Xodus graphical identity payload')
    except (ValueError, OSError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc))

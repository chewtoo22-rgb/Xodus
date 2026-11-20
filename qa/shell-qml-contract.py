#!/usr/bin/env python3
"""Render original shell QML and test SDDM API behavior using PySide6.

This checks theme code against QtQuick, with explicit mocks for SDDM. It does
not authenticate an account, replace a display manager, or simulate PAM.
"""
from pathlib import Path
import argparse
import os
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
from PySide6.QtCore import (QAbstractListModel, QModelIndex, QObject, Property,
                           Qt, QUrl, Signal, Slot, QMetaObject, Q_ARG)
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QRawFont
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--assets', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--font', type=Path, help='Load a local TTF for offscreen platforms without system fonts')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
assets = args.assets or repo / 'overlay/identity/assets'
args.output.mkdir(parents=True, exist_ok=True)


class ListModel(QAbstractListModel):
    def __init__(self, names):
        super().__init__()
        self.names = names

    def rowCount(self, parent=QModelIndex()):
        return len(self.names)

    def roleNames(self):
        return {Qt.UserRole + 1: b'name'}

    def data(self, index, role):
        if role == Qt.UserRole + 1 and index.isValid():
            return self.names[index.row()]
        return None

    count = Property(int, lambda self: len(self.names), constant=True)
    lastIndex = Property(int, lambda self: 0, constant=True)


class SddmMock(QObject):
    loginFailed = Signal()
    loginSucceeded = Signal()
    canReboot = Property(bool, lambda self: True, constant=True)
    canPowerOff = Property(bool, lambda self: True, constant=True)

    def __init__(self):
        super().__init__()
        self.calls = []

    @Slot(str, str, int)
    def login(self, user, password, session):
        self.calls.append(('login', user, password, session))

    @Slot()
    def reboot(self):
        self.calls.append(('reboot',))

    @Slot()
    def powerOff(self):
        self.calls.append(('powerOff',))


class KeyboardMock(QObject):
    capsLock = Property(bool, lambda self: False, constant=True)


application = QGuiApplication([])
if args.font:
    font_id = QFontDatabase.addApplicationFont(str(args.font.resolve()))
    assert font_id >= 0, args.font
    family = QFontDatabase.applicationFontFamilies(font_id)[0]
    QFont.insertSubstitution('Noto Sans', family)
    application.setFont(QFont(family))
assert QRawFont.fromFont(QFont('Noto Sans')).supportsCharacter(ord('X')), 'No usable render font loaded'
sddm = SddmMock()
users = ListModel(['liveuser', 'anotheruser'])
sessions = ListModel(['Plasma (Wayland)', 'Plasma (X11)'])
keyboard = KeyboardMock()
view = QQuickView()
view.setResizeMode(QQuickView.SizeRootObjectToView)
context = view.rootContext()
for name, value in [('sddm', sddm), ('userModel', users),
                    ('sessionModel', sessions), ('keyboard', keyboard)]:
    context.setContextProperty(name, value)
errors = []
view.engine().warnings.connect(lambda warnings: errors.extend(str(item) for item in warnings))


def local_artwork(source):
    return source.replace('file:///usr/share/wallpapers/Xodus/xodus-wallpaper.png',
                          QUrl.fromLocalFile(str((assets / 'xodus-wallpaper.png').resolve())).toString()
                          ).replace('file:///usr/share/pixmaps/xodus-app-icon.png',
                                    QUrl.fromLocalFile(str((assets / 'xodus-app-icon.png').resolve())).toString())


def flush():
    for _ in range(20):
        application.processEvents()


with tempfile.TemporaryDirectory(prefix='xodus-shell-qml-') as temporary:
    base = Path(temporary)
    login = base / 'Main.qml'
    login.write_text(local_artwork((repo / 'overlay/identity/shell/sddm/Main.qml').read_text(encoding='utf-8')),
                     encoding='utf-8')
    view.setSource(QUrl.fromLocalFile(str(login)))
    assert view.status() != QQuickView.Error, [str(error) for error in view.errors()]
    view.show()
    flush()
    root = view.rootObject()
    user = root.findChild(QObject, 'usernameField')
    password = root.findChild(QObject, 'passwordField')
    session = root.findChild(QObject, 'sessionSelector')
    button = root.findChild(QObject, 'signInButton')
    account = root.findChild(QObject, 'accountSelector')
    other_account = root.findChild(QObject, 'otherAccountButton')
    assert user.property('text') == 'liveuser'
    account.setProperty('currentIndex', 1)
    QMetaObject.invokeMethod(account, 'activated', Qt.DirectConnection, Q_ARG(int, 1))
    assert user.property('text') == 'anotheruser'
    QMetaObject.invokeMethod(other_account, 'clicked', Qt.DirectConnection)
    assert root.property('manualAccount') is True
    assert user.property('visible') is True
    assert user.property('text') == ''
    assert button.property('enabled') is False
    user.setProperty('text', '  anotheruser  ')
    password.setProperty('text', 'test-secret')
    session.setProperty('currentIndex', 1)
    QMetaObject.invokeMethod(button, 'clicked', Qt.DirectConnection)
    flush()
    assert sddm.calls[-1] == ('login', 'anotheruser', 'test-secret', 1), sddm.calls
    assert root.property('authenticating') is True
    assert button.property('enabled') is False
    QMetaObject.invokeMethod(button, 'clicked', Qt.DirectConnection)
    assert len(sddm.calls) == 1, sddm.calls
    sddm.loginFailed.emit()
    flush()
    assert root.property('authenticating') is False
    assert password.property('text') == ''
    assert 'Sign in failed' in root.property('loginMessage')
    # Empty-password accounts are supported; PAM decides whether to accept.
    QMetaObject.invokeMethod(button, 'clicked', Qt.DirectConnection)
    assert sddm.calls[-1] == ('login', 'anotheruser', '', 1)
    sddm.loginFailed.emit()
    root.setProperty('loginMessage', '')
    root.setProperty('manualAccount', False)
    account.setProperty('currentIndex', 0)
    user.setProperty('text', 'liveuser')
    session.setProperty('currentIndex', 0)
    for action, expected in [('restartButton', 'reboot'), ('powerOffButton', 'powerOff')]:
        QMetaObject.invokeMethod(root.findChild(QObject, action), 'clicked', Qt.DirectConnection)
        assert sddm.calls[-1] == (expected,)
    for width, height in [(1920, 1080), (1280, 720), (800, 600), (640, 480)]:
        view.resize(width, height)
        flush()
        assert view.grabWindow().save(str(args.output / f'xodus-login-{width}x{height}.png'))
    splash = base / 'Splash.qml'
    splash.write_text(local_artwork((repo / 'overlay/identity/shell/Splash.qml').read_text(encoding='utf-8')),
                      encoding='utf-8')
    view.setSource(QUrl.fromLocalFile(str(splash)))
    assert view.status() != QQuickView.Error, [str(error) for error in view.errors()]
    view.resize(1920, 1080)
    view.rootObject().setProperty('stage', 6)
    QTest.qWait(350)
    flush()
    assert abs(view.rootObject().findChild(QObject, 'progressFill').property('width') - 280) < 0.1
    assert view.grabWindow().save(str(args.output / 'xodus-session-splash.png'))
    # A machine without enumerated users still permits manual sign in.
    empty_users = ListModel([])
    context.setContextProperty('userModel', empty_users)
    view.setSource(QUrl())
    view.setSource(QUrl.fromLocalFile(str(login)))
    flush()
    root = view.rootObject()
    user = root.findChild(QObject, 'usernameField')
    assert user.property('visible') is True
    assert root.findChild(QObject, 'accountSelector').property('visible') is False
    user.setProperty('text', 'unenumerated')
    QMetaObject.invokeMethod(root.findChild(QObject, 'signInButton'), 'clicked', Qt.DirectConnection)
    assert sddm.calls[-1] == ('login', 'unenumerated', '', 0), sddm.calls
    assert not errors, errors
print('Shell QML contract: PASS (render, account/session forwarding, busy, failure, empty password, power actions)')

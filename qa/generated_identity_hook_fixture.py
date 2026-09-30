"""Execute the generated builder with controlled identity helper stubs.

The fixture performs ordinary writes in disposable directories. It never runs
the real compiler, package manager, installer, chroot or disk operations.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys


STUB = r'''from pathlib import Path
import os, stat, sys
action, args = sys.argv[1], sys.argv[2:]
profile = Path(os.environ['XODUS_TEST_PROFILE'])
live = Path(os.environ['XODUS_TEST_LIVE'])
source = os.environ['XODUS_TEST_SOURCE']
if action == 'dependencies':
    assert args[:3] == ['-S', '--needed', '--noconfirm']
    packages = set(args[3:])
    if 'qt5-base' in packages:
        assert {'qt5-base', 'pkgconf'} <= packages
        action = 'qt5-dependencies'
    else:
        assert {'cmake', 'ninja', 'qt6-base', 'qt6-declarative', 'qt6-5compat',
                'qt6-shadertools', 'qt6-svg', 'libx11'} <= packages
        action = 'qt6-dependencies'
with open(os.environ['XODUS_TEST_EVENT_LOG'], 'a') as log:
    log.write(action + '\n')
if os.environ.get('XODUS_TEST_FAIL_STAGE') == action:
    raise SystemExit(66)
if action in ('settings', 'welcome'):
    assert args == [str(profile), str(live)]
    path = live / 'usr/lib/xodus' / ('xodus-' + action)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\x7fELF disposable generated-hook app')
    path.chmod(0o755)
elif action in ('visible', 'calamares'):
    assert args == [str(live)]
elif action == 'shell':
    assert args == [str(live), str(profile / 'xodus-shell')]
elif action == 'frontend':
    assert args == [str(live / 'usr/share/pearOS-installer')]
    (Path(args[0]) / 'frontend-applied').write_text('Xodus frontend applied')
elif action == 'backend':
    expected = ['--apply-installer', str(live / 'usr/share/pearOS-installer'),
                '--original-root', str(live / 'usr/share/pearOS-installer'),
                '--source-commit', source, '--build-info', str(live / 'usr/lib/xodus/build-info')]
    assert args == expected, 'installer backend derivation arguments differ'
    assert (live / 'usr/share/pearOS-installer/frontend-applied').is_file(), 'frontend not applied first'
    info = (live / 'usr/lib/xodus/build-info').read_text().splitlines()
    assert info.count('XODUS_SOURCE_COMMIT=' + source) == 1
    for filename, executable in (('identity-payload.py', 'xodus-identity-payload'),
                                 ('restore-user-identity.py', 'xodus-restore-user-identity')):
        installed = live / 'usr/lib/xodus' / executable
        assert installed.read_bytes() == (profile / 'xodus-installed' / filename).read_bytes()
        assert stat.S_IMODE(installed.stat().st_mode) == 0o755, 'helper is not executable after customize'
elif action == 'boot-validation':
    assert args == ['--live-root', str(live)]
elif action == 'graphical-validation':
    assert args == [str(live), '--repo-root', str(profile / 'xodus-graphical-contract')]
elif action == 'capture':
    assert args == ['capture', str(live)]
    assert (live / 'usr/share/pearOS-installer/frontend-applied').exists()
elif action not in ('qt5-dependencies', 'qt6-dependencies'):
    raise AssertionError('unexpected helper invocation: ' + action)
'''

BUILD_RUNNER = r'''set -euo pipefail
source "$1"
profile=$2
pacstrap_dir=$3
buildmode=$4
_run_once() { "$1"; }
_msg_error() { printf '%s\n' "$1" >&2; exit "${2:-1}"; }
_make_customize_airootfs() {
  test ! -e "$pacstrap_dir/usr/lib/xodus/xodus-identity-payload"
  test ! -e "$pacstrap_dir/usr/lib/xodus/xodus-restore-user-identity"
  mkdir -p "$pacstrap_dir/usr/share/pearOS-installer"
  printf 'customize\n' >> "$XODUS_TEST_EVENT_LOG"
}
_make_bootmodes() { printf 'bootmodes\n' >> "$XODUS_TEST_EVENT_LOG"; }
_make_boot_on_iso9660() { printf 'netboot-modes\n' >> "$XODUS_TEST_EVENT_LOG"; }
_cleanup_pacstrap_dir() { printf 'cleanup\n' >> "$XODUS_TEST_EVENT_LOG"; }
_make_pkglist() { printf 'pkglist\n' >> "$XODUS_TEST_EVENT_LOG"; }
_prepare_airootfs_image() { printf 'squashfs\n' >> "$XODUS_TEST_EVENT_LOG"; }
_build_iso_base
'''


def run(builder, source_profile, scratch, source):
    scratch.mkdir()
    profile = scratch / 'profile'
    profile.mkdir()
    stub = scratch / 'stub.py'
    stub.write_text(STUB, encoding='utf-8')
    tools = scratch / 'tools'
    tools.mkdir()
    shell_helpers = {'xodus-settings/build-settings.sh': 'settings',
                     'xodus-build-welcome.sh': 'welcome',
                     'xodus-apply-visible-identity.sh': 'visible',
                     'xodus-apply-shell-identity.sh': 'shell'}
    python_helpers = {'xodus-installer/apply-installer-identity.py': 'frontend',
                      'xodus-installer/apply-calamares-identity.py': 'calamares',
                      'xodus-installed/derive-installer-identity.py': 'backend',
                      'xodus-installed/identity-payload.py': 'capture',
                      'xodus-installed/restore-user-identity.py': 'restore',
                      'xodus-boot-contract/verify-boot-identity.py': 'boot-validation',
                      'xodus-graphical-contract/qa/verify-graphical-identity.py': 'graphical-validation'}
    for relative, action in shell_helpers.items():
        path = profile / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/bash\nexec python3 "$XODUS_TEST_STUB" ' + action + ' "$@"\n')
    for relative, action in python_helpers.items():
        path = profile / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('import os, runpy, sys\nsys.argv = ["stub", "' + action + '", *sys.argv[1:]]\n'
                        'runpy.run_path(os.environ["XODUS_TEST_STUB"], run_name="__main__")\n')
    pacman = tools / 'pacman'
    pacman.write_text('#!/bin/bash\nexec python3 "$XODUS_TEST_STUB" dependencies "$@"\n')
    pacman.chmod(0o755)
    before_boot = ['customize', 'qt5-dependencies', 'qt6-dependencies', 'settings', 'welcome',
                   'visible', 'shell', 'frontend', 'calamares', 'backend', 'boot-validation',
                   'graphical-validation', 'capture']
    cases = [('iso', None), ('netboot', None), ('iso', 'frontend'),
             ('iso', 'boot-validation'), ('iso', 'graphical-validation')]
    for index, (mode, failure) in enumerate(cases):
        live = scratch / ('live-' + str(index))
        info = live / 'usr/lib/xodus/build-info'
        info.parent.mkdir(parents=True)
        shutil.copyfile(source_profile / 'airootfs/usr/lib/xodus/build-info', info)
        log = scratch / ('events-' + str(index))
        environment = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                           XODUS_TEST_PROFILE=str(profile), XODUS_TEST_LIVE=str(live),
                           XODUS_TEST_SOURCE=source, XODUS_TEST_STUB=str(stub),
                           XODUS_TEST_EVENT_LOG=str(log), XODUS_TEST_FAIL_STAGE=failure or '')
        result = subprocess.run(['bash', '-s', '--', str(builder), str(profile), str(live), mode],
                                input=BUILD_RUNNER, text=True, capture_output=True, env=environment)
        events = log.read_text().splitlines()
        if failure:
            assert result.returncode != 0, 'generated hook accepted failed ' + failure
            assert events == before_boot[:before_boot.index(failure) + 1], (failure, events, result.stderr)
        else:
            assert result.returncode == 0, result.stderr
            expected = before_boot + ['netboot-modes' if mode == 'netboot' else 'bootmodes',
                                      'cleanup', 'pkglist', 'squashfs']
            assert events == expected, ('generated build order differs', events)
    print('Generated identity hook staging, source, mode and failure ordering: PASS')


if __name__ == '__main__':
    run(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])

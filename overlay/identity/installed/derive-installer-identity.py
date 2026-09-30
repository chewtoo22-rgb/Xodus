#!/usr/bin/env python3
"""Derive only reviewed graphical identity hooks from the pinned installer.

Verification recomputes the result from audited Git objects. A receipt with a
new self-consistent hash cannot authorize a changed disk or account operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

INSTALLER_COMMIT = 'e676698b4a07f797a50fd25241a738ead75248e6'
ORIGINAL_BLOBS = {
    'system_install/setup': '99046db1958c0f7fe6710f3e7236a6bc2cc4fdde',
    'post-install/post_setup': '784e109f47f4ff906392c5027679d5d81ce76652',
}
RECEIPT = 'xodus-installed-identity.json'
SHA = re.compile(r'^[0-9a-f]{40}$')


def fail(message):
    raise ValueError('Xodus installer derivation: ' + message)


def regular(root, relative, required=True):
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            fail('symlink in installer path: ' + relative)
        if candidate != path and candidate.exists() and not candidate.is_dir():
            fail('non-directory installer parent: ' + relative)
    if root not in path.resolve().parents or (path.exists() and not path.is_file()):
        fail('unsafe installer file: ' + relative)
    if required and not path.is_file():
        fail('missing installer file: ' + relative)
    return path


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=True)
    return result.stdout


def originals(root):
    if git(root, 'rev-parse', 'HEAD').decode().strip() != INSTALLER_COMMIT:
        fail('audited source checkout is not at the pinned installer commit')
    result = {}
    for relative, expected in ORIGINAL_BLOBS.items():
        if git(root, 'rev-parse', 'HEAD:' + relative).decode().strip() != expected:
            fail('pinned installer Git blob changed: ' + relative)
        data = git(root, 'show', 'HEAD:' + relative)
        if regular(root, relative).read_bytes() != data:
            fail('audited checkout has modified protected script: ' + relative)
        result[relative] = data
    return result


def build_source(build_info, expected):
    if not SHA.fullmatch(expected) or build_info.is_symlink() or not build_info.is_file():
        fail('missing exact Xodus source or safe extracted build-info')
    text = build_info.read_text()
    for key, value in (('XODUS_SOURCE_COMMIT', expected),
                       ('XODUS_INSTALLER_COMMIT', INSTALLER_COMMIT)):
        values = re.findall('^' + key + '=([^\n]*)$', text, re.M)
        if values != [value]:
            fail('build-info differs from expected ' + key)


def exact(text, old, new, label):
    if text.count(old) != 1 or new in text:
        fail('pinned script anchor changed: ' + label)
    return text.replace(old, new)


def derive(raw, source):
    setup = raw['system_install/setup'].decode('utf-8')
    payload = '/usr/lib/xodus/xodus-identity-payload'
    invocation = f'python3 {payload} install --source-root / --target-root /mnt --expected-source {source}'
    preflight = f'''  # Check the reviewed live identity before any destructive operation.
  if ! python3 {payload} verify --source-root / --expected-source {source}; then
    error_exit "Xodus graphical identity payload failed verification"
  fi

'''
    setup = exact(setup, '  # Set/load the US keymap\n', preflight + '  # Set/load the US keymap\n', 'pre-destructive identity verification')
    boot = f'''  # Stage Xodus boot files before any installed initramfs is rebuilt.
  if ! {invocation} --phase boot; then
    error_exit "Failed to stage Xodus boot identity"
  fi

'''
    setup = exact(setup, '  # Partition layout work:\n', boot + '  # Partition layout work:\n', 'boot transfer order')
    setup = exact(setup,
                  '  arch-chroot /mnt plymouth-set-default-theme -R pear-plymouth 2>/dev/null || echo "Warning: Failed to set plymouth theme" >> /home/liveuser/Desktop/install.log',
                  '''  if ! arch-chroot /mnt plymouth-set-default-theme -R xodus; then
    error_exit "Failed to rebuild installed Xodus Plymouth theme"
  fi
  if [[ "$(arch-chroot /mnt plymouth-set-default-theme)" != xodus ]]; then
    error_exit "Installed Plymouth theme is not Xodus"
  fi''', 'installed Plymouth selector')
    setup = exact(setup,
                  '  echo "GRUB_THEME=\\"/usr/share/grub/themes/pearOS/theme.txt\\"" >> /mnt/etc/default/grub',
                  '''  sed -i 's|^GRUB_THEME=.*|GRUB_THEME="/usr/share/grub/themes/Xodus/theme.txt"|' /mnt/etc/default/grub''', 'installed GRUB theme selector')
    setup = exact(setup, '  echo "Name=pearOS Post Install"', '  echo "Name=Xodus Post Install"', 'post-install launcher name')
    setup = exact(setup, '  echo "Icon=nicec0re-logo"', '  echo "Icon=/usr/share/pixmaps/xodus-app-icon.png"', 'post-install launcher icon')
    full = f'''  # Package cleanup is complete; retain the qualified graphical identity.
  if ! {invocation} --phase full; then
    error_exit "Failed to apply installed Xodus graphical identity"
  fi

'''
    setup = exact(setup, '  # Sends the install finished messages to the frontend\n', full + '  # Sends the install finished messages to the frontend\n', 'full transfer after package cleanup')
    post = raw['post-install/post_setup'].decode('utf-8')
    post = exact(post, 'Name=pearOS First Theme Setup', 'Name=Xodus First Theme Setup', 'first-theme launcher label')
    post = exact(post, '    SDDM_THEMES="pearOS pearOS-dark"', '    SDDM_THEMES="Xodus pearOS pearOS-dark"', 'new login theme avatar')
    post = exact(post, 'Current=pearOS\nEOF', 'Current=Xodus\nEOF', 'post-setup login theme selector')
    # This heredoc runs once in the real user's first Plasma session, after the
    # upstream switcher. The helper never creates an additional autostart entry.
    post = exact(post, '"$THEME_SWITCHER" --$THEME_MODE\nrm -f "$FIRST_THEME_DESKTOP"\nrm -f "\\$0"',
                 '''"$THEME_SWITCHER" --$THEME_MODE
/usr/lib/xodus/xodus-restore-user-identity --home "$USER_HOME"
xodus_restore_status=\\$?
rm -f "$FIRST_THEME_DESKTOP"
rm -f "\\$0"
exit "\\$xodus_restore_status"''', 'restore after first-theme reset')
    post = exact(post, '=== pearOS Post-Install Script Started:', '=== Xodus Post-Install Script Started:', 'post-setup start label')
    post = exact(post, '=== pearOS Installation Script Completed:', '=== Xodus Installation Script Completed:', 'post-setup end label')
    post = exact(post, 'Description=Remove pearOS default live user', 'Description=Remove Xodus default setup user', 'default removal service description')
    return {'system_install/setup': setup.encode(), 'post-install/post_setup': post.encode()}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def receipt(raw, changed, source):
    return (json.dumps({
        'schema': 1, 'transform': 'xodus-installed-identity-v1',
        'installer_commit': INSTALLER_COMMIT, 'source_commit': source,
        'original': {path: {'git_blob': ORIGINAL_BLOBS[path], 'sha256': sha256(data)}
                     for path, data in sorted(raw.items())},
        'derived': {path: {'sha256': sha256(data)} for path, data in sorted(changed.items())},
    }, indent=2) + '\n').encode()


def process(embedded, original_root, source, build_info, verify):
    if embedded.is_symlink() or not embedded.is_dir() or original_root.is_symlink() or not original_root.is_dir():
        fail('installer and audited source must be real directories')
    embedded, original_root = embedded.resolve(strict=True), original_root.resolve(strict=True)
    if embedded == Path('/') or original_root == Path('/'):
        fail('installer paths must be staged directories')
    build_source(build_info, source)
    raw = originals(original_root)
    changed = derive(raw, source)
    expected_receipt = receipt(raw, changed, source)
    files = {path: regular(embedded, path) for path in changed}
    receipt_path = regular(embedded, RECEIPT, required=verify)
    if verify:
        for relative, data in changed.items():
            if files[relative].read_bytes() != data:
                fail('embedded installer differs from deterministic derivation: ' + relative)
        if receipt_path.read_bytes() != expected_receipt:
            fail('installer derivation receipt does not match audited source and exact bytes')
    else:
        if receipt_path.exists():
            fail('installer identity derivation already exists')
        for relative, data in raw.items():
            if files[relative].read_bytes() != data:
                fail('frontend must preserve protected installer script: ' + relative)
        for relative, data in changed.items():
            files[relative].write_bytes(data)
        receipt_path.write_bytes(expected_receipt)
        receipt_path.chmod(0o644)
    print(('Verified' if verify else 'Derived') + ' Xodus installer identity from exact audited Git blobs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply-installer', type=Path)
    mode.add_argument('--verify-installer', type=Path)
    parser.add_argument('--original-root', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--build-info', type=Path, required=True)
    args = parser.parse_args()
    try:
        process(args.verify_installer or args.apply_installer, args.original_root,
                args.source_commit, args.build_info, args.verify_installer is not None)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc))

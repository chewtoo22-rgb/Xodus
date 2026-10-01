#!/usr/bin/env python3
"""Verify the Control Center frontend against the exact archived settings package."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('package', type=Path)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
overlay = repo / 'overlay/identity/control-center'
helper = overlay / 'apply-control-center-identity.py'
lock = json.loads((overlay / 'source.lock.json').read_text())
spec = importlib.util.spec_from_file_location('control_center', helper)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)
prefix = 'usr/share/plasma/plasmoids/PearControlCentre/'
assert hashlib.sha256(args.package.read_bytes()).hexdigest() == lock['package']['sha256']


def snapshot(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob('*') if p.is_file()}


def apply(directory, success):
    result = subprocess.run(['python3', str(helper), str(directory)], capture_output=True, text=True)
    assert (result.returncode == 0) == success, result.stdout + result.stderr


with tempfile.TemporaryDirectory(prefix='xodus-control-contract-') as temporary:
    base = Path(temporary)
    original = base / 'original'
    with tarfile.open(args.package) as archive:
        info = dict(line.split(' = ', 1) for line in archive.extractfile('.PKGINFO').read().decode().splitlines()
                    if line.startswith(('pkgname = ', 'pkgver = ')))
        assert info == {'pkgname': lock['package']['name'], 'pkgver': lock['package']['version']}
        for member in archive:
            if member.isfile() and member.name.startswith(prefix):
                target = original / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    metadata_path = original / prefix / 'metadata.json'
    assert hashlib.sha256(metadata_path.read_bytes()).hexdigest() == lock['raw_metadata_sha256']
    metadata = json.loads(metadata_path.read_bytes())
    legal = {key: metadata['KPlugin'][key] for key in ('Authors', 'License', 'Website', 'Id')}
    metadata['KPlugin']['Name'] = 'Xodus Control Center'
    metadata['KPlugin']['Description'] = 'Xodus control center based on the work of prayag2'
    metadata_path.write_bytes((json.dumps(metadata, ensure_ascii=False, indent=4) + '\n').encode())
    before = snapshot(original)

    current = base / 'current'
    shutil.copytree(original, current)
    apply(current, True)
    after = snapshot(current)
    modified = {name for name in before if before[name] != after[name]}
    allowed = {'contents/ui/main.qml', 'contents/ui/FullRepresentation.qml',
               'contents/ui/CompactRepresentation.qml', 'contents/ui/config/configAppearance.qml',
               'contents/config/main.xml',
               *('contents/ui/components/' + name + '.qml' for name in
                 ('NetworkBtn', 'Volume', 'DndButton', 'BrightnessSlider'))}
    assert modified == {prefix + name for name in allowed}, modified
    for name in ('NetworkBtn', 'Volume', 'DndButton', 'BrightnessSlider'):
        path = prefix + 'contents/ui/components/' + name + '.qml'
        closing = before[path].rfind(b'}')
        assert after[path].startswith(before[path][:closing]), name
        assert after[path].endswith(before[path][closing:]), name
    assert {key: json.loads(after[prefix + 'metadata.json'])['KPlugin'][key] for key in legal} == legal
    assert len(set(after) - set(before)) == len(lock['payload']) + 1 == 9
    assert set(control.TRANSFER_FILES) == set(after)
    assert control.verify(current, payload=overlay)['files'] == 110
    assert b'layouts/Xodus.qml' in after[prefix + 'contents/ui/FullRepresentation.qml']
    assert b'Screen.desktopAvailableHeight' in after[prefix + 'contents/ui/main.qml']
    assert b'- 96))' in after[prefix + 'contents/ui/main.qml']
    assert b'i18n("Tahoe")' not in after[prefix + 'contents/ui/config/configAppearance.qml']
    config = ET.fromstring(after[prefix + 'contents/config/main.xml'])
    defaults = {entry.attrib['name']: entry.find('{*}default').text for entry in config.findall('.//{*}entry')}
    assert defaults['layout'] == '0' and defaults['scale'] == '100'
    assert defaults['toggleButtonsColor'] == '#ad85f5'
    assert defaults['customButtonImage'] == '../assets/xodus-controls.svg'

    forged = base / 'forged'
    shutil.copytree(current, forged)
    (forged / prefix / 'contents/ui/xodus/Controller.qml').write_text('import QtQuick\nItem {}\n')
    # A receipt cannot bless modified controller bytes.
    try:
        control.verify(forged, payload=overlay)
    except SystemExit:
        pass
    else:
        raise AssertionError('modified deployed controller was accepted')
    (current / control.RECEIPT).write_text('{}\n')
    try:
        control.verify(current, payload=overlay)
    except SystemExit:
        pass
    else:
        raise AssertionError('forged derivation receipt was accepted')

    for name in ('contents/ui/components/Network.qml', 'contents/ui/pages/SystemSessionActionsPage.qml',
                 'contents/config/main.xml', 'metadata.json'):
        drift = base / 'drift'
        shutil.copytree(original, drift)
        target = drift / prefix / name
        target.write_bytes(target.read_bytes() + b'\n// unexpected drift\n')
        snapshot_before = snapshot(drift)
        apply(drift, False)
        assert snapshot(drift) == snapshot_before
        shutil.rmtree(drift)
    unknown = base / 'unknown'
    shutil.copytree(original, unknown)
    (unknown / prefix / 'contents/ui/Unreviewed.qml').write_text('import QtQuick\nItem {}\n')
    snapshot_before = snapshot(unknown)
    apply(unknown, False)
    assert snapshot(unknown) == snapshot_before
    linked = base / 'linked'
    shutil.copytree(original, linked)
    path = linked / prefix / 'contents/ui/components/Network.qml'
    original_bytes = path.read_bytes()
    path.unlink()
    external = base / 'external-network.qml'
    external.write_bytes(original_bytes)
    path.symlink_to(external)
    apply(linked, False)
    assert external.read_bytes() == original_bytes
print('PASS: exact package, 17 frontend outputs, 111 closed transfer files, retained verification and drift rejection')

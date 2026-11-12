"""Extend retained-image fixtures with actual reviewed graphical components.

XODUS_GUI_PACKAGE_DIR must contain the three pinned archives. No network or
installer execution is performed. Existing native-app, account and desktop
inventory fixtures remain; package-backed appearance components replace only
their own files and the reviewed KDE configuration/palette defaults.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HELPERS = {'toolkit': 'apply-toolkit-identity.py', 'desktop': 'apply-desktop-identity.py',
           'control-center': 'apply-control-center-identity.py', 'dock': 'apply-dock-identity.py'}
_VALIDATED_ARCHIVES = {}


def _load(name, path):
    spec = importlib.util.spec_from_file_location('fixture_xodus_' + name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(root, relative, data, mode=0o644):
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink() or (candidate != path and candidate.exists() and not candidate.is_dir()):
            raise ValueError('Unsafe graphical fixture destination: ' + str(relative))
    if (root not in path.resolve().parents or (path.exists() and not path.is_file()) or
            (path.is_file() and path.stat().st_nlink != 1)):
        raise ValueError('Graphical fixture path escapes its root: ' + str(relative))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


def _archive(directory, name, version, expected):
    path = directory / (name + '-' + version + '.pkg.tar.zst')
    if not path.is_file() or path.is_symlink():
        raise ValueError('Missing pinned GUI fixture archive: ' + str(path))
    stat = path.stat()
    identity = (str(path.resolve()), stat.st_size, stat.st_mtime_ns, expected)
    if identity not in _VALIDATED_ARCHIVES:
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError('GUI fixture archive pin differs: ' + str(path))
        _VALIDATED_ARCHIVES[identity] = True
    return path


def _extract(root, archive, members):
    # Exact reviewed archives and closed package members; no arbitrary root or
    # account tree extraction. Runtime helpers inspect original file hashes next.
    for relative in members:
        path = root / relative
        candidates = [path, *path.parents]
        if path.is_dir() and not path.is_symlink():
            candidates.extend(path.rglob('*'))
        for candidate in candidates:
            if candidate == root:
                continue
            if candidate.is_symlink() or (candidate.is_file() and candidate.stat().st_nlink != 1):
                raise ValueError('Unsafe package extraction fixture path: ' + str(relative))
    subprocess.run(['tar', '--zstd', '--no-same-owner', '--no-same-permissions',
                    '-xf', str(archive), '-C', str(root), *sorted(set(members))], check=True)


def populate(root, reference, repo):
    """Populate and apply actual toolkit/desktop/control-center/dock components.

    Return exact deployed file paths, copied trusted references and archive pins
    for callers creating squashfs/extraction fixtures. Stock KDE dependencies
    are explicit controlled stand-ins; this function tests identity contracts.
    """
    root, reference, repo = (Path(path) for path in (root, reference, repo))
    for path in (root, reference, repo):
        if path.is_symlink() or not path.is_dir() or path.resolve() == Path('/'):
            raise ValueError('Graphical fixture needs real non-host-root directories')
    root, reference, repo = (path.resolve(strict=True) for path in (root, reference, repo))
    if root == reference or root in reference.parents or reference in root.parents:
        raise ValueError('Graphical fixture root and reference overlap')
    configured = os.environ.get('XODUS_GUI_PACKAGE_DIR')
    if not configured:
        raise ValueError('Set XODUS_GUI_PACKAGE_DIR to the three pinned GUI archive directory')
    directory = Path(configured).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError('XODUS_GUI_PACKAGE_DIR must be a directory')

    references = []
    for component, filename in HELPERS.items():
        source = repo / 'overlay/identity' / component
        if not (source / filename).is_file():
            raise ValueError('Missing reviewed graphical fixture helper: ' + str(source / filename))
        for path in source.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                if path.is_symlink():
                    raise ValueError('Graphical fixture reference contains a symlink')
                relative = path.relative_to(repo).as_posix()
                # All repository text is canonical LF; PNG assets retain exact bytes.
                data = path.read_bytes() if path.suffix == '.png' else path.read_text(encoding='utf-8').encode()
                _write(reference, relative, data)
                references.append(relative)
    modules = {name: _load(name, reference / 'overlay/identity' / name / filename)
               for name, filename in HELPERS.items()}
    toolkit, desktop, control, dock = (modules[name] for name in ('toolkit', 'desktop', 'control-center', 'dock'))
    toolkit_lock = json.loads((toolkit.HERE / 'source.lock.json').read_text())
    control_lock = json.loads((control.HERE / 'source.lock.json').read_text())
    dock_lock = json.loads((dock.PAYLOAD / 'source.lock.json').read_text())
    packages = {
        'pearos-settings': _archive(directory, toolkit_lock['package'], toolkit_lock['version'], toolkit_lock['archive_sha256']),
        'system-settings': _archive(directory, toolkit_lock['switcher']['package'], toolkit_lock['switcher']['version'], toolkit_lock['switcher']['archive_sha256']),
        'pearos-dock': _archive(directory, dock_lock['package'], dock_lock['version'], dock_lock['package_sha256']),
    }
    if control_lock['package']['sha256'] != toolkit_lock['archive_sha256']:
        raise ValueError('Control Center and toolkit source package pins disagree')
    _extract(root, packages['pearos-settings'],
             [path for path in toolkit_lock['files'] if path not in toolkit.SWITCHER['FILES']] + [control.BASE.as_posix()])
    _extract(root, packages['system-settings'], list(toolkit.SWITCHER['FILES']))
    _extract(root, packages['pearos-dock'],
             [(dock.CONTENTS / name).as_posix() for name in dock_lock['source_files']] +
             [(dock.CONTENTS / 'skins' / name).as_posix() for name in dock_lock['upstream_skin_files']])
    for relative in toolkit.HOME_FILES:
        _write(root, 'home/liveuser/' + relative, (root / 'etc/skel' / relative).read_bytes())

    # Reproduce precisely the Name/Description mutation done by the base shell
    # hook. Authors, licenses and plugin/backend identity remain from the package.
    metadata = root / control.BASE / 'metadata.json'
    if hashlib.sha256(metadata.read_bytes()).hexdigest() != control_lock['raw_metadata_sha256']:
        raise ValueError('Raw Control Center metadata pin differs')
    document = json.loads(metadata.read_text())
    if document.get('KPlugin', {}).get('Name') != 'PearControlCentre':
        raise ValueError('Unexpected raw Control Center frontend name')
    document['KPlugin']['Name'] = 'Xodus Control Center'
    document['KPlugin']['Description'] = 'Xodus control center based on the work of prayag2'
    metadata.write_text(json.dumps(document, ensure_ascii=False, indent=4) + '\n')

    for home in ('etc/skel', 'home/liveuser'):
        for name in desktop.CONFIGS:
            source = repo / 'qa/fixtures/desktop-identity' / name
            _write(root, home + '/.config/' + name, source.read_text().encode())
    palette_path = 'overlay/identity/shell/Xodus.colors'
    palette = (repo / palette_path).read_text().encode()
    _write(reference, palette_path, palette)
    _write(root, 'usr/share/color-schemes/Xodus.colors', palette)
    for relative in desktop.DEPENDENCIES + ('usr/lib/qt6/plugins/org.kde.kdecoration3/org.kde.breeze.so',):
        if not (root / relative).exists():
            _write(root, relative, b'Controlled stock KDE dependency fixture; not executable.\n')

    def package_query(command, **kwargs):
        if command[:1] != ['arch-chroot'] or command[2:4] != ['/usr/bin/pacman', '-Q']:
            raise ValueError('Unexpected command in graphical fixture: ' + repr(command))
        package = command[-1]
        versions = {'pearos-settings': toolkit_lock['version'], 'system-settings': toolkit_lock['switcher']['version']}
        return subprocess.CompletedProcess(command, 0, package + ' ' + versions[package] + '\n', '')
    with contextlib.redirect_stdout(io.StringIO()):
        with patch.object(toolkit.subprocess, 'run', package_query):
            toolkit.apply(root)
        desktop.apply(root)
        control.apply(root)
        dock.apply(root, dock.PAYLOAD, dock_lock)
        toolkit.verify(root)
        desktop.verify(root)
        control.verify(root)
        dock.verify(root)
    files = set()
    for module in modules.values():
        files.update(module.TRANSFER_FILES)
        for relative in getattr(module, 'USER_CONFIGS', ()):
            if relative.startswith('.'):
                files.update(home + '/' + relative for home in ('etc/skel', 'home/liveuser'))
            else:
                files.add(relative)
    return {'files': sorted(files), 'references': sorted(set(references) | {palette_path}),
            'packages': {name: path.name for name, path in packages.items()}}

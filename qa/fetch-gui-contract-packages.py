#!/usr/bin/env python3
"""Fetch exact package inputs for source and retained-image contract tests."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REPO = Path(__file__).resolve().parents[1]


def packages():
    toolkit = json.loads((REPO / 'overlay/identity/toolkit/source.lock.json').read_text())
    dock = json.loads((REPO / 'overlay/identity/dock/source.lock.json').read_text())
    release = json.loads((REPO / 'overlay/identity/settings/release-source.lock.json').read_text())
    return (
        (toolkit['package'], toolkit['version'], toolkit['archive_sha256']),
        (toolkit['switcher']['package'], toolkit['switcher']['version'], toolkit['switcher']['archive_sha256']),
        (dock['package'], dock['version'], dock['package_sha256']),
        ('pearos-notch', '26.6.1-1', '4251b0c484f9037a7ee306eb5696867d18039323a2216ee7bdd75cc2619b6b73'),
        ('filesystem', release['version'], release['package_sha256']),
    )


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def fetch(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, version, sha in packages():
        target = directory / (name + '-' + version + '.pkg.tar.zst')
        if target.is_symlink():
            raise ValueError('Unsafe GUI input path: ' + str(target))
        if not target.exists():
            url = 'https://mirror.pearos.xyz/main/x86_64/' + name + '-' + version + '-x86_64.pkg.tar.zst'
            temporary = target.with_suffix('.download')
            if temporary.exists() or temporary.is_symlink():
                raise ValueError('GUI download destination already exists: ' + str(temporary))
            with urllib.request.urlopen(url, timeout=60) as source, temporary.open('xb') as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    output.write(chunk)
            if digest(temporary) != sha:
                raise ValueError('Downloaded GUI archive differs: ' + name)
            temporary.rename(target)
        if not target.is_file() or digest(target) != sha:
            raise ValueError('GUI archive differs: ' + name)
        print(name + ' ' + version + ' sha256=' + sha)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    fetch(parser.parse_args().directory)

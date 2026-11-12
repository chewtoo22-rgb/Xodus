#!/usr/bin/env python3
"""Validate a retained manifest before using its paths as SquashFS selectors."""
import argparse
import importlib.util
import json
from pathlib import Path
import re


def extract_paths(manifest, source, helper):
    if not re.fullmatch('[0-9a-f]{40}', source):
        raise ValueError('expected source must be an exact commit')
    spec = importlib.util.spec_from_file_location('reviewed_identity_payload', helper)
    payload = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(payload)
    document = json.loads(manifest.read_text())
    if (set(document) != {'schema', 'source_commit', 'files'} or
            document['schema'] != 1 or document['source_commit'] != source or
            not isinstance(document['files'], list)):
        raise ValueError('manifest schema or source differs from reviewed build')
    required = set(payload.FIXED) | payload.BOOT_REQUIRED
    allowed = required | set(payload.OPTIONAL)
    paths = []
    for entry in document['files']:
        if not isinstance(entry, dict) or set(entry) != {'path', 'sha256', 'mode'}:
            raise ValueError('invalid manifest entry')
        path = entry['path']
        if not isinstance(path, str) or path not in allowed:
            raise ValueError('manifest contains an unreviewed extraction path')
        if (entry['mode'] != payload.file_mode(path) or
                not isinstance(entry['sha256'], str) or
                not re.fullmatch('[0-9a-f]{64}', entry['sha256'])):
            raise ValueError('manifest contains an invalid mode or hash')
        paths.append(path)
    if paths != sorted(set(paths)) or not required <= set(paths):
        raise ValueError('manifest inventory is incomplete, duplicated or unordered')
    return paths


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--expected-source', required=True)
    args = parser.parse_args()
    helper = Path(__file__).resolve().parents[1] / 'overlay/identity/installed/identity-payload.py'
    try:
        paths = extract_paths(args.manifest, args.expected_source, helper)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit('Unsafe identity extraction manifest: ' + str(exc))
    print('\n'.join(paths))

"""Reject unsafe manifests before retained ISO extraction."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'overlay/identity/installed/identity-payload.py'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


selector = module('extraction_selector', ROOT / 'qa/identity-payload-extract-paths.py')


class ExtractionManifestContract(unittest.TestCase):
    def setUp(self):
        payload = module('payload_paths', HELPER)
        self.document = {'schema': 1, 'source_commit': 'a' * 40, 'files': [
            {'path': path, 'mode': payload.file_mode(path), 'sha256': 'b' * 64}
            for path in sorted(set(payload.FIXED) | payload.BOOT_REQUIRED)]}

    def check(self, document):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'manifest.json'
            manifest.write_text(json.dumps(document))
            return selector.extract_paths(manifest, 'a' * 40, HELPER)

    def test_closed_manifest_accepts_reviewed_inventory(self):
        self.assertEqual(self.check(self.document), [entry['path'] for entry in self.document['files']])

    def test_rejects_path_escape_or_unreviewed_payload(self):
        for path in ('../etc/shadow', '/etc/shadow', 'usr/lib/xodus/arbitrary-program'):
            document = copy.deepcopy(self.document)
            document['files'][0]['path'] = path
            with self.assertRaises(ValueError):
                self.check(document)

    def test_rejects_missing_duplicate_and_reordered_inventory(self):
        for entries in (self.document['files'][1:],
                        self.document['files'] + [self.document['files'][-1]],
                        list(reversed(self.document['files']))):
            document = copy.deepcopy(self.document)
            document['files'] = entries
            with self.assertRaises(ValueError):
                self.check(document)

    def test_rejects_source_and_schema_changes(self):
        for key, value in (('source_commit', 'c' * 40), ('schema', 2)):
            document = copy.deepcopy(self.document)
            document[key] = value
            with self.assertRaises(ValueError):
                self.check(document)

    def test_rejects_bad_hash_or_mode(self):
        for key, value in (('mode', '0777'), ('sha256', 'not-a-digest')):
            document = copy.deepcopy(self.document)
            document['files'][0][key] = value
            with self.assertRaises(ValueError):
                self.check(document)


if __name__ == '__main__':
    unittest.main()

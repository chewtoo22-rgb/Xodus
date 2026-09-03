from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qa"))

from ai_labs_readiness_contract import reject_duplicate_keys  # noqa: E402


class AiLabsReadinessContractTests(unittest.TestCase):
    def test_rejects_duplicate_manifest_key(self) -> None:
        payload = '{"schema": 1, "schema": 2}'
        with self.assertRaisesRegex(ValueError, "duplicate key: schema"):
            json.loads(payload, object_pairs_hook=reject_duplicate_keys)

    def test_accepts_unique_manifest_keys(self) -> None:
        payload = '{"schema": 1, "target": "intel-nuc-x86_64"}'
        self.assertEqual(
            json.loads(payload, object_pairs_hook=reject_duplicate_keys),
            {"schema": 1, "target": "intel-nuc-x86_64"},
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qa"))

from ai_labs_readiness_contract import reject_duplicate_keys  # noqa: E402


def test_rejects_duplicate_manifest_key() -> None:
    payload = '{"schema": 1, "schema": 2}'
    with pytest.raises(ValueError, match="duplicate key: schema"):
        json.loads(payload, object_pairs_hook=reject_duplicate_keys)


def test_accepts_unique_manifest_keys() -> None:
    payload = '{"schema": 1, "target": "intel-nuc-x86_64"}'
    assert json.loads(payload, object_pairs_hook=reject_duplicate_keys) == {
        "schema": 1,
        "target": "intel-nuc-x86_64",
    }

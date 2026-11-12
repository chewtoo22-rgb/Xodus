#!/usr/bin/env python3
"""Regression tests for the AST import allowlist in qa/x1_ai_offline_boundary.py."""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qa"))

import x1_ai_offline_boundary as boundary  # noqa: E402

TARGET = pathlib.Path("scripts/xodus-ai-verify-artifact.py")


class AllowlistTests(unittest.TestCase):
    def test_trust_boundary_scripts_are_clean(self) -> None:
        for path in boundary.ALLOWLISTED_SCRIPTS:
            with self.subTest(path=str(path)):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertEqual(boundary.allowlist_errors(path, text), [])

    def test_rejects_network_and_dynamic_imports(self) -> None:
        injections = (
            "import http.client", "import ssl", "import ftplib", "import asyncio", "import socket",
            "from urllib import request", '__import__("so" + "cket")', "from importlib import import_module",
            'import importlib\nimportlib.import_module("socket")', 'exec("import socket")',
            'eval("1")', 'compile("x", "f", "exec")', "from . import sibling",
        )
        for snippet in injections:
            with self.subTest(snippet=snippet):
                self.assertTrue(boundary.allowlist_errors(TARGET, "import json\n" + snippet + "\n"))

    def test_allows_method_named_compile(self) -> None:
        self.assertEqual(boundary.allowlist_errors(TARGET, 'import re\nX = re.compile("a")\n'), [])


if __name__ == "__main__":
    unittest.main()

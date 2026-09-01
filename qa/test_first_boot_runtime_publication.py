#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest import mock

MODULE_PATH = pathlib.Path(__file__).with_name("first-boot-runtime-acceptance.py")
spec = importlib.util.spec_from_file_location("acceptance", MODULE_PATH)
acceptance = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(acceptance)


class PublicationTests(unittest.TestCase):
    def test_publishes_new_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "acceptance.json"
            acceptance.publish_output(out, '{"status":"pass"}\n')
            self.assertEqual(out.read_text(encoding="utf-8"), '{"status":"pass"}\n')
            self.assertEqual(list(pathlib.Path(td).glob(".acceptance.json.*.tmp")), [])

    def test_refuses_existing_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "acceptance.json"
            out.write_text("old\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                acceptance.publish_output(out, "new\n")
            self.assertEqual(out.read_text(encoding="utf-8"), "old\n")

    def test_refuses_symlink_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            real = root / "real.json"
            real.write_text("old\n", encoding="utf-8")
            out = root / "acceptance.json"
            out.symlink_to(real)
            with self.assertRaisesRegex(ValueError, "already exists"):
                acceptance.publish_output(out, "new\n")
            self.assertEqual(real.read_text(encoding="utf-8"), "old\n")

    def test_refuses_symlink_parent(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            real_parent = root / "real"
            real_parent.mkdir()
            alias = root / "alias"
            alias.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "non-symlink directory"):
                acceptance.publish_output(alias / "acceptance.json", "new\n")
            self.assertFalse((real_parent / "acceptance.json").exists())

    def test_cleans_temp_file_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            out = root / "acceptance.json"
            with mock.patch.object(os, "replace", side_effect=OSError("forced replace failure")):
                with self.assertRaisesRegex(OSError, "forced replace failure"):
                    acceptance.publish_output(out, "new\n")
            self.assertFalse(out.exists())
            self.assertEqual(list(root.glob(".acceptance.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("desktop_session_launcher_contract.py")
spec = importlib.util.spec_from_file_location("desktop_session_launcher_contract", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

DesktopSessionContractError = module.DesktopSessionContractError
validate_root = module.validate_root


class DesktopSessionLauncherContractTest(unittest.TestCase):
    def make_root(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "usr/share/wayland-sessions").mkdir(parents=True)
        (root / "usr/bin").mkdir(parents=True)
        return root

    def install_executable(self, root: Path, name: str = "xodus-session") -> Path:
        path = root / "usr/bin" / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    def write_entry(self, root: Path, exec_value: str, name: str = "xodus.desktop") -> Path:
        entry = root / "usr/share/wayland-sessions" / name
        entry.write_text(
            "[Desktop Entry]\nName=Xodus\nType=Application\nExec=" + exec_value + "\n",
            encoding="utf-8",
        )
        return entry

    def assert_rejected(self, root: Path, contains: str) -> None:
        with self.assertRaises(DesktopSessionContractError) as caught:
            validate_root(root)
        self.assertIn(contains, str(caught.exception))

    def test_accepts_bare_command_resolved_inside_root(self) -> None:
        root = self.make_root()
        self.install_executable(root)
        self.write_entry(root, "xodus-session --mode desktop")
        result = validate_root(root)
        self.assertEqual(1, len(result))
        self.assertEqual("xodus-session", result[0].command)
        self.assertEqual("/usr/bin/xodus-session", result[0].resolved_command)

    def test_accepts_absolute_command_inside_root(self) -> None:
        root = self.make_root()
        self.install_executable(root)
        self.write_entry(root, "/usr/bin/xodus-session")
        result = validate_root(root)
        self.assertEqual("/usr/bin/xodus-session", result[0].resolved_command)

    def test_rejects_missing_command(self) -> None:
        root = self.make_root()
        self.write_entry(root, "missing-session")
        self.assert_rejected(root, "not installed")

    def test_rejects_shell_wrapper(self) -> None:
        root = self.make_root()
        self.install_executable(root, "bash")
        self.write_entry(root, "/usr/bin/bash -lc xodus-session")
        self.assert_rejected(root, "wrapper is not allowed")

    def test_rejects_relative_command_path(self) -> None:
        root = self.make_root()
        self.write_entry(root, "../bin/xodus-session")
        self.assert_rejected(root, "relative command path")

    def test_rejects_non_executable_target(self) -> None:
        root = self.make_root()
        target = root / "usr/bin/xodus-session"
        target.write_text("not executable\n", encoding="utf-8")
        target.chmod(0o644)
        self.write_entry(root, "xodus-session")
        self.assert_rejected(root, "not an executable regular file")

    def test_rejects_entry_symlink(self) -> None:
        root = self.make_root()
        self.install_executable(root)
        real = root / "real.desktop"
        real.write_text("[Desktop Entry]\nExec=xodus-session\n", encoding="utf-8")
        (root / "usr/share/wayland-sessions/xodus.desktop").symlink_to(real)
        self.assert_rejected(root, "regular non-symlink")

    def test_rejects_session_directory_symlink(self) -> None:
        root = self.make_root()
        actual = root / "actual-sessions"
        actual.mkdir()
        (root / "usr/share/wayland-sessions").rmdir()
        (root / "usr/share/wayland-sessions").symlink_to(actual)
        self.assert_rejected(root, "session directory must be a real directory")

    def test_rejects_duplicate_exec_keys(self) -> None:
        root = self.make_root()
        self.install_executable(root)
        entry = root / "usr/share/wayland-sessions/xodus.desktop"
        entry.write_text(
            "[Desktop Entry]\nExec=xodus-session\nExec=xodus-session --other\n",
            encoding="utf-8",
        )
        self.assert_rejected(root, "exactly one")

    def test_rejects_launcher_symlink_escape(self) -> None:
        root = self.make_root()
        outside_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_tmp.cleanup)
        outside = Path(outside_tmp.name) / "outside-session"
        outside.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        outside.chmod(0o755)
        (root / "usr/bin/xodus-session").symlink_to(outside)
        self.write_entry(root, "xodus-session")
        self.assert_rejected(root, "escapes installed root")

    def test_rejects_no_session_entries(self) -> None:
        root = self.make_root()
        self.assert_rejected(root, "no desktop session entries")


if __name__ == "__main__":
    unittest.main()

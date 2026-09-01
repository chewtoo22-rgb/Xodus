#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from systemd_dependency_integrity import validate


def write_unit(root: Path, name: str, unit_lines: str) -> None:
    (root / name).write_text("[Unit]\n" + unit_lines + "\n[Service]\nType=oneshot\nExecStart=/bin/true\n", encoding="utf-8")


class SystemdDependencyIntegrityTests(unittest.TestCase):
    def test_valid_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_unit(root, "xodus-first.service", "Before=xodus-ai.service")
            write_unit(root, "xodus-ai.service", "After=xodus-first.service\nRequires=xodus-first.service")
            validate(root)

    def test_missing_internal_dependency_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_unit(root, "xodus-first.service", "After=xodus-missing.service")
            with self.assertRaisesRegex(ValueError, "missing Xodus unit"):
                validate(root)

    def test_after_cycle_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_unit(root, "xodus-a.service", "After=xodus-b.service")
            write_unit(root, "xodus-b.service", "After=xodus-a.service")
            with self.assertRaisesRegex(ValueError, "ordering cycle"):
                validate(root)

    def test_before_cycle_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_unit(root, "xodus-a.service", "Before=xodus-b.service")
            write_unit(root, "xodus-b.service", "Before=xodus-a.service")
            with self.assertRaisesRegex(ValueError, "ordering cycle"):
                validate(root)

    def test_mutual_wants_does_not_create_ordering_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_unit(root, "xodus-a.service", "Wants=xodus-b.service")
            write_unit(root, "xodus-b.service", "Wants=xodus-a.service")
            validate(root)

    def test_external_system_unit_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_unit(root, "xodus-first.service", "After=local-fs.target network.service")
            validate(root)

    def test_symlink_unit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real.service"
            target.write_text("[Service]\nType=oneshot\n", encoding="utf-8")
            (root / "xodus-link.service").symlink_to(target.name)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                validate(root)

    def test_symlinked_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real_root = base / "real-units"
            real_root.mkdir()
            write_unit(real_root, "xodus-first.service", "After=local-fs.target")
            linked_root = base / "units"
            linked_root.symlink_to(real_root.name, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "traverses symlink component"):
                validate(linked_root)

    def test_symlinked_ancestor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real_parent = base / "real-parent"
            real_root = real_parent / "units"
            real_root.mkdir(parents=True)
            write_unit(real_root, "xodus-first.service", "After=local-fs.target")
            linked_parent = base / "linked-parent"
            linked_parent.symlink_to(real_parent.name, target_is_directory=True)
            candidate = linked_parent / "units"
            self.assertFalse(candidate.is_symlink())
            self.assertTrue(candidate.is_dir())
            with self.assertRaisesRegex(ValueError, "traverses symlink component"):
                validate(candidate)

    def test_empty_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "no Xodus service units"):
                validate(Path(tmp))


if __name__ == "__main__":
    unittest.main()

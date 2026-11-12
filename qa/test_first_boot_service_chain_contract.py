#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("first_boot_service_chain_contract.py")
spec = importlib.util.spec_from_file_location("first_boot_service_chain_contract", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

SOURCE = Path(__file__).resolve().parents[1] / "overlay" / "first-boot"


class ServiceChainContractTests(unittest.TestCase):
    def fixture(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        for filename in module.UNITS.values():
            shutil.copy2(SOURCE / filename, root / filename)
        return root

    def mutate(self, root: Path, filename: str, old: str, new: str) -> None:
        path = root / filename
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_chain_passes(self):
        module.validate(SOURCE)

    def test_ai_cannot_run_before_base_completion(self):
        root = self.fixture()
        self.mutate(root, module.UNITS["ai"], "ConditionPathExists=/var/lib/xodus/first-boot/complete\n", "")
        with self.assertRaises(ValueError):
            module.validate(root)

    def test_runtime_requires_ai_service(self):
        root = self.fixture()
        self.mutate(root, module.UNITS["runtime"], "Requires=xodus-ai-first-boot.service\n", "")
        with self.assertRaises(ValueError):
            module.validate(root)

    def test_network_dependency_is_rejected(self):
        root = self.fixture()
        self.mutate(root, module.UNITS["runtime"], "After=xodus-ai-first-boot.service", "After=xodus-ai-first-boot.service network-online.target")
        with self.assertRaises(ValueError):
            module.validate(root)

    def test_extra_writable_path_is_rejected(self):
        root = self.fixture()
        self.mutate(root, module.UNITS["runtime"], "ReadWritePaths=/var/lib/xodus/ai", "ReadWritePaths=/var/lib/xodus/ai /etc")
        with self.assertRaises(ValueError):
            module.validate(root)

    def test_shell_indirection_is_rejected(self):
        root = self.fixture()
        self.mutate(root, module.UNITS["base"], "ExecStart=/usr/lib/xodus/xodus-first-boot", "ExecStart=/bin/sh -c /usr/lib/xodus/xodus-first-boot")
        with self.assertRaises(ValueError):
            module.validate(root)

    def test_symlinked_unit_is_rejected(self):
        root = self.fixture()
        target = root / module.UNITS["runtime"]
        real = root / "runtime.real"
        target.rename(real)
        target.symlink_to(real.name)
        with self.assertRaises(ValueError):
            module.validate(root)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
import importlib.util
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "xodus-arena-capabilities"
loader = SourceFileLoader("arena_capabilities", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class ArenaCapabilitiesTest(unittest.TestCase):
    def test_unknown_hardware_fails_closed(self):
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.dict(os.environ, {"XODUS_ARENA_DRM_ROOT": root}, clear=False), \
             mock.patch.object(module, "command", return_value=False):
            data = module.snapshot()
        self.assertEqual(data["gpu_vendors"], ["unknown"])
        self.assertFalse(data["arena"]["session_ready"])
        self.assertFalse(data["graphics"]["dlss_may_be_available"])
        self.assertTrue(data["policy"]["read_only_probe"])
        self.assertFalse(data["policy"]["hardware_validation_claim"])

    def test_vendor_detection_is_deterministic(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            for card, vendor in (("card2", "0x8086"), ("card0", "0x10de"), ("card1", "0x1002")):
                path = base / card / "device"
                path.mkdir(parents=True)
                (path / "vendor").write_text(vendor)
            with mock.patch.dict(os.environ, {"XODUS_ARENA_DRM_ROOT": root}, clear=False):
                self.assertEqual(module.gpu_vendors(), ["amd", "intel", "nvidia"])

    def test_graphics_options_require_prerequisites(self):
        with mock.patch.object(module, "gpu_vendors", return_value=["nvidia"]), \
             mock.patch.object(module, "command", side_effect=lambda name: name == "gamescope"), \
             mock.patch.object(module, "service_available", return_value=False):
            data = module.snapshot()
        self.assertTrue(data["graphics"]["dlss_may_be_available"])
        self.assertTrue(data["graphics"]["nis_requires_gamescope_and_nvidia"])
        self.assertFalse(data["arena"]["steam_ready"])

    def test_session_type_is_bounded(self):
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "WAYLAND"}, clear=False):
            self.assertEqual(module.session_type(), "wayland")
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "mystery"}, clear=False):
            self.assertEqual(module.session_type(), "unknown")


if __name__ == "__main__":
    unittest.main()

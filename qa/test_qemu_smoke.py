#!/usr/bin/env python3
"""Behavioral checks for the host boot gate with a simulated QEMU process."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().with_name("qemu-smoke.sh")


class QemuSmokeContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.iso = self.root / "Xodus.iso"
        self.iso.write_bytes(b"mock ISO")
        self.code = self.root / "OVMF_CODE.fd"
        self.vars = self.root / "OVMF_VARS.fd"
        self.code.write_bytes(b"code")
        self.vars.write_bytes(b"vars")
        self.logs = self.root / "logs"
        self._executable(
            "xorriso",
            """#!/usr/bin/env bash
if [[ ${MOCK_XORRISO_MODE:-efi} == efi ]]; then
  echo '-e /EFI/BOOT/efiboot.img'
else
  echo '-no-emul-boot'
fi
""",
        )
        self._executable(
            "qemu-system-x86_64",
            """#!/usr/bin/env bash
case "${MOCK_QEMU_MODE:-idle}" in
  ready) printf 'XODUS_LIVE_DESKTOP_READY\\r\\n'; exec sleep 8 ;;
  idle) exec sleep 8 ;;
  partial) printf 'XODUS_LIVE_DESKTOP_READY_extra\\r\\n'; exec sleep 8 ;;
  embedded) printf 'firmware: XODUS_LIVE_DESKTOP_READY\\r\\n'; exec sleep 8 ;;
  exited) printf 'XODUS_LIVE_DESKTOP_READY\\r\\n'; exit 0 ;;
  *) exit 9 ;;
esac
""",
        )

    def _executable(self, name, body):
        path = self.bin / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def run_gate(self, mode="idle", **overrides):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin}:{env['PATH']}",
                "BOOT_SECONDS": "2",
                "OVMF_CODE_PATH": str(self.code),
                "OVMF_VARS_PATH": str(self.vars),
                "MOCK_QEMU_MODE": mode,
            }
        )
        env.update(overrides)
        return subprocess.run(
            ["bash", str(SCRIPT), str(self.iso), str(self.logs)],
            env=env,
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )

    def test_exact_live_guest_marker_passes(self):
        result = self.run_gate("ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("result=pass", (self.logs / "smoke-summary.txt").read_text())

    def test_qemu_surviving_timeout_is_not_a_pass(self):
        result = self.run_gate("idle")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("result=fail", (self.logs / "smoke-summary.txt").read_text())

    def test_old_log_marker_is_truncated_before_boot(self):
        self.logs.mkdir()
        (self.logs / "serial.log").write_text("XODUS_LIVE_DESKTOP_READY\n")
        result = self.run_gate("idle")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("XODUS_LIVE_DESKTOP_READY", (self.logs / "serial.log").read_text())

    def test_partial_or_embedded_marker_does_not_pass(self):
        for mode in ("partial", "embedded"):
            with self.subTest(mode=mode):
                result = self.run_gate(mode)
                self.assertNotEqual(result.returncode, 0)

    def test_marker_from_exited_qemu_does_not_pass(self):
        result = self.run_gate("exited")
        self.assertNotEqual(result.returncode, 0)

    def test_missing_efi_path_fails_before_qemu(self):
        result = self.run_gate("ready", MOCK_XORRISO_MODE="noefi")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.logs / "serial.log").exists())


if __name__ == "__main__":
    unittest.main()

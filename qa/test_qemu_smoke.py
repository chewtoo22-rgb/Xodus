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
        self.qemu_args = self.root / "qemu-args.txt"
        self.qmp_server = self.root / "mock-qmp-server.py"
        self.qmp_server.write_text(
            """import json
import socket
import sys
import time

arguments = sys.argv[1:]
address = arguments[arguments.index('-qmp') + 1]
path = address.removeprefix('unix:').split(',')[0]
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path)
server.listen(2)
server.settimeout(8)
deadline = time.monotonic() + 8
while time.monotonic() < deadline:
    try:
        connection, _ = server.accept()
    except TimeoutError:
        break
    with connection:
        stream = connection.makefile('rwb', buffering=0)
        stream.write(b'{"QMP":{}}\\n')
        while True:
            line = stream.readline()
            if not line:
                break
            request = json.loads(line)
            command = request['execute']
            if command == 'screendump':
                with open(request['arguments']['filename'], 'wb') as image:
                    image.write(b'P6\\n1 1\\n255\\n\\x00\\x00\\x00')
            result = {'status': 'running'} if command == 'query-status' else {}
            stream.write((json.dumps({'id': request['id'], 'return': result}) + '\\n').encode())
""",
            encoding="utf-8",
        )
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
printf '%s\\n' "$@" > "$MOCK_QEMU_ARGS"
case "${MOCK_QEMU_MODE:-idle}" in
  ready) printf 'XODUS_LIVE_DESKTOP_READY\\r\\n'; exec sleep 8 ;;
  idle) exec sleep 8 ;;
  qmp) exec python3 "$MOCK_QMP_SERVER" "$@" ;;
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
                "MOCK_QEMU_ARGS": str(self.qemu_args),
                "MOCK_QMP_SERVER": str(self.qmp_server),
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
        args = self.qemu_args.read_text().splitlines()
        self.assertEqual(args[args.index("-display") + 1], f"vnc=unix:{self.logs}/guest-vnc.sock")
        self.assertIn("qmp=socket_unavailable", (self.logs / "qmp-status.log").read_text())

    def test_qmp_captures_screen_and_status_without_guest_marker(self):
        result = self.run_gate("qmp")
        self.assertNotEqual(result.returncode, 0)
        diagnostics = (self.logs / "qmp-status.log").read_text()
        self.assertIn('query-status={"id": "query-status", "return": {"status": "running"}}', diagnostics)
        self.assertIn("screendump=", diagnostics)
        self.assertTrue((self.logs / "guest-screen-final.ppm").is_file())

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
        self.assertIn(
            "reason=qemu_exited_before_desktop_ready",
            (self.logs / "smoke-summary.txt").read_text(),
        )

    def test_missing_efi_path_fails_before_qemu(self):
        result = self.run_gate("ready", MOCK_XORRISO_MODE="noefi")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.logs / "serial.log").exists())


if __name__ == "__main__":
    unittest.main()

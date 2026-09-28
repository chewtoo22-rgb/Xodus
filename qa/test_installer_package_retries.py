"""Exercise the generated nautilus recovery with a fake pacman boundary."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "scripts/patch-installer-package-retries.py"


class NautilusRecoveryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = PATCHER.read_text()
        assignments = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id in {"old", "old_dm"}:
                    assignments[target.id] = ast.literal_eval(node.value)

        cls.work = tempfile.TemporaryDirectory()
        work = Path(cls.work.name)
        original = work / "upstream-setup"
        patched = work / "patched-setup"
        original.write_text(
            "#!/usr/bin/env bash\n" + assignments["old"] + assignments["old_dm"],
            newline="\n",
        )
        subprocess.run([sys.executable, str(PATCHER), str(original), str(patched)], check=True, capture_output=True)
        # The patcher writes text using the host default newline. Bash fixtures
        # are run through Git Bash on Windows, so keep the generated copy LF.
        patched.write_bytes(patched.read_bytes().replace(b"\r\n", b"\n"))
        subprocess.run(["bash", "-n", patched.name], cwd=work, check=True)

        script = patched.read_text()
        start = script.index("        nautilus)\n")
        end = script.index("          ;;\n", start) + len("          ;;\n")
        fallback_start = script.index("      # Never fall back to unqualified pearOS nautilus", end)
        fallback_end = script.index("      if $recovered; then", fallback_start)
        cls.recovery = (script[start:end] + "      esac\n" + script[fallback_start:fallback_end]).replace(
            "/home/liveuser/Desktop/install.log", '"$MOCK_INSTALL_LOG"'
        )
        cls.mock_script = work / "run-recovery.sh"
        cls.mock_script.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
arch-chroot() {
  [[ "${1:-}" == /mnt && "${2:-}" == pacman ]] || return 90
  shift 2
  printf '%s\\n' "$*" >> "$MOCK_CALLS"
  case "$*" in
    '-Q libnautilus-extension')
      [[ "$MOCK_EXT_PRE" != missing ]] || return 1
      if [[ -e "$MOCK_INSTALLED" ]]; then
        printf 'libnautilus-extension %s\\n' "$MOCK_EXT_AFTER"
      else
        printf 'libnautilus-extension %s\\n' "$MOCK_EXT_PRE"
      fi ;;
    '-Q nautilus')
      [[ -e "$MOCK_INSTALLED" ]] || return 1
      printf 'nautilus %s\\n' "$MOCK_NAUTILUS_AFTER" ;;
    '-Dk') [[ "$MOCK_DK_OK" == yes ]] ;;
    *) return 91 ;;
  esac
}
pacman() {
  printf 'host-pacman %s\\n' "$*" >> "$MOCK_CALLS"
  [[ "$*" == '-Sp --print-format %r/%n %v extra/nautilus' ]] || return 92
  printf '%s\\n' "$MOCK_REPO_ROWS"
}
pacstrap() {
  printf 'pacstrap %s\\n' "$*" >> "$MOCK_CALLS"
  if [[ "$*" == '/mnt extra/nautilus' ]]; then
    [[ "$MOCK_INSTALL_OK" == yes ]] || return 1
    touch "$MOCK_INSTALLED"
    return 0
  fi
  # An accidental generic fallback would appear to succeed; the contract
  # must prove the nautilus case refuses that route.
  return 0
}
package=nautilus
recovered=false
database_refresh_ok="$MOCK_REFRESH_OK"
case "$package" in
"""
            + cls.recovery
            + "printf 'recovered=%s\\n' \"$recovered\"\n",
            newline="\n",
        )
        subprocess.run(["bash", "-n", cls.mock_script.name], cwd=work, check=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.work.cleanup()

    def run_recovery(
        self,
        *,
        extension: str = "50.3.1-1",
        repo_rows: str = "extra/nautilus 50.3.1-1",
        installed_nautilus: str = "50.3.1-1",
        installed_extension: str = "50.3.1-1",
        install_ok: bool = True,
        database_ok: bool = True,
        refresh_ok: bool = True,
    ) -> tuple[str, str]:
        with tempfile.TemporaryDirectory(dir=self.mock_script.parent) as temp:
            work = Path(temp)
            env = os.environ.copy()
            env.update(
                MOCK_CALLS="calls",
                MOCK_INSTALLED="installed",
                MOCK_INSTALL_LOG="install.log",
                MOCK_EXT_PRE=extension,
                MOCK_REPO_ROWS=repo_rows,
                MOCK_NAUTILUS_AFTER=installed_nautilus,
                MOCK_EXT_AFTER=installed_extension,
                MOCK_INSTALL_OK="yes" if install_ok else "no",
                MOCK_DK_OK="yes" if database_ok else "no",
                MOCK_REFRESH_OK="true" if refresh_ok else "false",
            )
            if os.name == "nt":
                # Windows invokes this shell through WSL's bash.exe, which
                # forwards only variables named in WSLENV.
                forwarded = ":".join(key for key in env if key.startswith("MOCK_"))
                env["WSLENV"] = ":".join(filter(None, (env.get("WSLENV"), forwarded)))
            result = subprocess.run(
                ["bash", "../" + self.mock_script.name],
                cwd=work,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (work / "calls").read_text() if (work / "calls").exists() else ""
            self.assertNotIn("pacstrap /mnt nautilus", calls)
            self.assertNotIn("--overwrite", calls)
            self.assertNotIn("-Rdd", calls)
            return result.stdout.strip(), calls

    def test_matching_official_version_recovers_without_a_dated_pin(self) -> None:
        for version in ("50.3.1-1", "51.0-2"):
            with self.subTest(version=version):
                outcome, calls = self.run_recovery(
                    extension=version,
                    repo_rows=f"extra/nautilus {version}\nextra/some-dependency 1.0-1",
                    installed_nautilus=version,
                    installed_extension=version,
                )
                self.assertEqual(outcome, "recovered=true")
                self.assertIn("pacstrap /mnt extra/nautilus", calls)
                self.assertIn("-Dk", calls)

    def test_version_mismatch_fails_without_retrying_pearos(self) -> None:
        outcome, calls = self.run_recovery(repo_rows="extra/nautilus 48.7-1")
        self.assertEqual(outcome, "recovered=false")
        self.assertNotIn("pacstrap /mnt extra/nautilus", calls)

    def test_foreign_or_ambiguous_repository_result_fails(self) -> None:
        for rows in (
            "pearos/nautilus 50.3.1-1",
            "extra/nautilus 50.3.1-1\nextra/nautilus 50.3.1-1",
        ):
            with self.subTest(rows=rows):
                outcome, calls = self.run_recovery(repo_rows=rows)
                self.assertEqual(outcome, "recovered=false")
                self.assertNotIn("pacstrap /mnt extra/nautilus", calls)

    def test_missing_extension_or_failed_install_fails(self) -> None:
        for kwargs in ({"extension": "missing"}, {"install_ok": False}, {"refresh_ok": False}):
            with self.subTest(kwargs=kwargs):
                outcome, _ = self.run_recovery(**kwargs)
                self.assertEqual(outcome, "recovered=false")

    def test_postinstall_mismatch_or_database_failure_fails(self) -> None:
        for kwargs in (
            {"installed_nautilus": "48.7-1"},
            {"installed_extension": "48.7-1"},
            {"database_ok": False},
        ):
            with self.subTest(kwargs=kwargs):
                outcome, calls = self.run_recovery(**kwargs)
                self.assertEqual(outcome, "recovered=false")
                self.assertIn("pacstrap /mnt extra/nautilus", calls)


if __name__ == "__main__":
    unittest.main()

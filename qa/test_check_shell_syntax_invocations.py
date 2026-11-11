from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qa"))

from check_shell_syntax_invocations import violations_in  # noqa: E402


class ShellSyntaxInvocationTests(unittest.TestCase):
    def test_rejects_multiple_operands(self) -> None:
        self.assertEqual(len(violations_in("bash -n a.sh b.sh\n")), 1)

    def test_rejects_array_expansion(self) -> None:
        self.assertEqual(len(violations_in('  bash -n "${scripts[@]}"\n')), 1)

    def test_rejects_yaml_run_line(self) -> None:
        self.assertEqual(len(violations_in("        run: bash -n x.sh y.sh\n")), 1)

    def test_accepts_single_operand(self) -> None:
        self.assertEqual(violations_in('bash -n "$script"\nbash -n qa/x.sh\n'), [])

    def test_accepts_loop_form(self) -> None:
        text = 'for script in a.sh b.sh; do bash -n "$script"; done\n'
        self.assertEqual(violations_in(text), [])

    def test_accepts_chained_single_checks(self) -> None:
        self.assertEqual(violations_in("bash -n a.sh && bash -n b.sh\n"), [])

    def test_ignores_comment_lines(self) -> None:
        self.assertEqual(violations_in("# bash -n a.sh b.sh\n"), [])

    def test_accepts_single_operand_forms(self) -> None:
        for line in (
            "bash -n -- a.sh",
            "bash -n a.sh 2>/dev/null",
            "bash -n a.sh >/dev/null 2>&1",
            "bash -n a.sh 2>&1 | tee x",
            "bash -n a.sh < /dev/null",
            "bash -n a.sh &",
            'bash -n "$(dirname "$0")/a.sh"',
            'bash -n "$script" || exit 1',
            "bash -c 'echo a b'",
            "bash qa/run.sh a b",
            "./build.sh -n a b",
        ):
            with self.subTest(line=line):
                self.assertEqual(violations_in(line + "\n"), [])

    def test_rejects_multi_file_forms(self) -> None:
        for line in (
            'bash -n "$a" "$b"',
            "bash -n *.sh",
            "bash -n $scripts",
            "bash -nv a.sh b.sh",
            "bash -O extglob -n a.sh b.sh",
            "bash -n do-build.sh x.sh",
            "sh -n a.sh b.sh",
            "if bash -n a.sh b.sh; then :; fi",
        ):
            with self.subTest(line=line):
                self.assertEqual(len(violations_in(line + "\n")), 1)

    def test_bash_really_skips_later_operands(self) -> None:
        """Pin the bash behaviour this contract exists to guard against."""
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp, "good.sh")
            bad = Path(tmp, "bad.sh")
            good.write_text("echo ok\n")
            bad.write_text("if then fi(\n")
            multi = subprocess.run(["bash", "-n", str(good), str(bad)], capture_output=True)
            single = subprocess.run(["bash", "-n", str(bad)], capture_output=True)
        self.assertEqual(multi.returncode, 0)
        self.assertNotEqual(single.returncode, 0)

    def test_repository_is_clean(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "qa" / "check_shell_syntax_invocations.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qa"))

import xodus_studio_templates_contract as contract  # noqa: E402
from xodus_studio_templates_contract import ContractError, load, validate  # noqa: E402

SCAFFOLDER = ROOT / "scripts" / "xodus-studio-new.py"
_spec = importlib.util.spec_from_file_location("xodus_studio_new", SCAFFOLDER)
new_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(new_mod)

PLACEHOLDER = contract.PLACEHOLDER
# CI's Arch container sets this so a missing toolchain fails instead of skipping.
REQUIRE_SMOKE = os.environ.get("XODUS_STUDIO_REQUIRE_SMOKE") == "1"
CARGO_HOME_BIN = Path.home() / ".cargo" / "bin"


class TemplateTree:
    """A disposable copy of studio/templates for filesystem-level negative tests."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name, "templates")
        shutil.copytree(contract.TEMPLATES_DIR, self.root, symlinks=True)
        self.data = load(self.root / contract.MANIFEST_NAME)

    def cleanup(self) -> None:
        self._tmp.cleanup()


class TemplatesContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = TemplateTree()
        self.addCleanup(self.tree.cleanup)
        self.root = self.tree.root
        self.data = self.tree.data

    def rejects(self, fn=None, pattern: str = "") -> None:
        data = copy.deepcopy(self.data)
        if fn is not None:
            fn(data)
        with self.assertRaisesRegex(ContractError, pattern):
            validate(data, root=self.root)

    def test_repository_templates_are_valid(self) -> None:
        packages = validate(load())
        for pkg in ("godot", "love", "raylib", "sdl3", "rust", "cmake"):
            self.assertIn(pkg, packages)
        self.assertEqual(set(load()["templates"]),
                         {"godot-2d", "love2d", "raylib-c", "rust-cli-game", "sdl3-c"})

    def test_copy_is_valid(self) -> None:
        validate(self.data, root=self.root)

    def test_rejects_unknown_top_level_key(self) -> None:
        self.rejects(lambda d: d.__setitem__("post_install", "curl | sh"), "unexpected")

    def test_rejects_missing_key(self) -> None:
        self.rejects(lambda d: d.pop("placeholder"), "missing")

    def test_rejects_boolean_schema(self) -> None:
        self.rejects(lambda d: d.__setitem__("schema", True), "schema")

    def test_rejects_changed_placeholder(self) -> None:
        self.rejects(lambda d: d.__setitem__("placeholder", "{{name}}"), "placeholder")

    def test_rejects_network(self) -> None:
        self.rejects(lambda d: d.__setitem__("network_required", True), "network")

    def test_rejects_unknown_template_key(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"].__setitem__("hooks", []), "unexpected")

    def test_rejects_unknown_profile(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"].__setitem__("profiles", ["engines", "ghost"]), "unknown studio")

    def test_rejects_empty_profiles(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"].__setitem__("profiles", []), "empty")

    def test_rejects_unsorted_templates(self) -> None:
        def flip(d):
            d["templates"] = dict(reversed(list(d["templates"].items())))
        self.rejects(flip, "sorted")

    def test_rejects_unlisted_file(self) -> None:
        (self.root / "love2d" / "extra.lua").write_text("print(1)\n")
        self.rejects(pattern=r"unlisted \['extra.lua'\]")

    def test_rejects_missing_listed_file(self) -> None:
        (self.root / "love2d" / "main.lua").unlink()
        self.rejects(pattern=r"missing \['main.lua'\]")

    def test_rejects_symlinked_file(self) -> None:
        target = self.root / "love2d" / "main.lua"
        target.unlink()
        target.symlink_to("/etc/passwd")
        self.rejects(pattern="symlink")

    def test_rejects_symlinked_directory(self) -> None:
        shutil.rmtree(self.root / "raylib-c" / "src")
        (self.root / "raylib-c" / "src").symlink_to(self.root / "sdl3-c" / "src")
        self.rejects(pattern="symlink")

    def test_rejects_symlinked_template_dir(self) -> None:
        shutil.rmtree(self.root / "love2d")
        (self.root / "love2d").symlink_to(self.root / "godot-2d")
        self.rejects(pattern="symlink")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs mkfifo")
    def test_rejects_fifo(self) -> None:
        os.mkfifo(self.root / "love2d" / "pipe")
        self.rejects(pattern="non-regular")

    def test_rejects_directory_without_manifest_entry(self) -> None:
        (self.root / "orphan").mkdir()
        self.rejects(pattern="do not match")

    def test_rejects_manifest_entry_without_directory(self) -> None:
        shutil.rmtree(self.root / "love2d")
        self.rejects(pattern="do not match")

    def test_rejects_stray_root_file(self) -> None:
        (self.root / "notes.txt").write_text("x\n")
        self.rejects(pattern="unexpected files")

    def test_rejects_path_traversal_in_files(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["files"].insert(0, "../escape"), "invalid path")

    def test_rejects_absolute_path_in_files(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["files"].insert(0, "/etc/passwd"), "relative")

    def test_rejects_placeholder_in_path(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["files"].append(f"{PLACEHOLDER}.lua"), "placeholder")

    def test_rejects_unsorted_files(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["files"].reverse(), "sorted")

    def test_rejects_missing_readme(self) -> None:
        (self.root / "love2d" / "README.md").unlink()

        def drop(d):
            t = d["templates"]["love2d"]
            t["files"].remove("README.md")
            t["placeholder_files"].remove("README.md")
        self.rejects(drop, "README")

    def test_rejects_placeholder_missing_from_marked_file(self) -> None:
        path = self.root / "love2d" / "conf.lua"
        path.write_text(path.read_text().replace(PLACEHOLDER, "hardcoded"))
        self.rejects(pattern="placeholder expected")

    def test_rejects_placeholder_in_unmarked_file(self) -> None:
        path = self.root / "love2d" / "main.lua"
        path.write_text(path.read_text() + f"-- {PLACEHOLDER}\n")
        self.rejects(pattern="placeholder expected")

    def test_rejects_unknown_token(self) -> None:
        path = self.root / "love2d" / "main.lua"
        path.write_text(path.read_text() + "-- __XODUS_PROJECT_NAM__\n")
        self.rejects(pattern="unknown token")

    def test_rejects_nul_byte(self) -> None:
        path = self.root / "love2d" / "main.lua"
        path.write_bytes(path.read_bytes() + b"\0")
        self.rejects(pattern="NUL")

    def test_rejects_non_utf8(self) -> None:
        path = self.root / "love2d" / "main.lua"
        path.write_bytes(path.read_bytes() + b"\xff\n")
        self.rejects(pattern="UTF-8")

    def test_rejects_oversized_template(self) -> None:
        path = self.root / "love2d" / "main.lua"
        path.write_text(path.read_text() + "-- pad\n" * contract.MAX_SOURCE_LINES)
        self.rejects(pattern="source lines")

    def test_rejects_smoke_package_outside_profiles(self) -> None:
        self.rejects(lambda d: d["templates"]["rust-cli-game"]["smoke"]["packages"].append("godot"),
                     "not installed by profiles")

    def test_rejects_smoke_step_with_unlisted_tool(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["smoke"]["steps"].append(["sh", "-c", "id"]),
                     "not a listed tool")

    def test_rejects_shell_string_step(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["smoke"]["steps"].append(["luajit", "-bl main.lua; id"]),
                     "not allowed")

    def test_rejects_traversal_in_smoke_arg(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["smoke"]["steps"].append(["luajit", "-bl", "../x.lua"]),
                     "not allowed")

    def test_rejects_absolute_smoke_arg(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["smoke"]["steps"].append(["luajit", "/tmp/x.lua"]),
                     "not allowed")

    def test_rejects_empty_smoke_steps(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["smoke"].__setitem__("steps", []), "non-empty")

    def test_rejects_pkg_config_probe_without_tool(self) -> None:
        def strip(d):
            d["templates"]["sdl3-c"]["smoke"]["tools"].remove("pkg-config")
        self.rejects(strip, "pkg-config")

    def test_rejects_unknown_smoke_key(self) -> None:
        self.rejects(lambda d: d["templates"]["love2d"]["smoke"].__setitem__("shell", "id"), "unexpected")

    def test_rejects_duplicate_json_key(self) -> None:
        path = self.root / contract.MANIFEST_NAME
        path.write_text('{"schema": 1, "schema": 1}')
        with self.assertRaisesRegex(ContractError, "duplicate key"):
            load(path)

    def test_rejects_symlinked_manifest(self) -> None:
        path = self.root / contract.MANIFEST_NAME
        real = self.root.parent / "real.json"
        path.rename(real)
        path.symlink_to(real)
        with self.assertRaisesRegex(ContractError, "regular file"):
            load(path)

    def test_cli_print_packages(self) -> None:
        out = subprocess.run([sys.executable, str(ROOT / "qa" / "xodus_studio_templates_contract.py"),
                              "--print-packages"], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.split(), sorted(out.stdout.split()))
        self.assertIn("sdl3", out.stdout.split())


class ScaffolderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = new_mod.load_manifest()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def scaffold(self, template: str, name: str, dest: Path) -> dict:
        plan, files = new_mod.build_plan(self.manifest, template, name, dest)
        new_mod.write_files(dest, files)
        return plan

    def test_every_template_scaffolds_and_substitutes(self) -> None:
        for tid, spec in self.manifest["templates"].items():
            with self.subTest(template=tid):
                dest = self.tmp / tid
                plan = self.scaffold(tid, "space_game-2", dest)
                self.assertFalse(plan["executed"])
                self.assertFalse(plan["network_used"])
                written = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
                self.assertEqual(written, spec["files"])
                for rel in spec["files"]:
                    text = (dest / rel).read_text(encoding="utf-8")
                    self.assertNotIn(PLACEHOLDER, text)
                    self.assertNotIn("__XODUS_", text)
                    if rel in spec["placeholder_files"]:
                        self.assertIn("space_game-2", text)
                    self.assertEqual(oct((dest / rel).stat().st_mode & 0o777), oct(0o644 & ~_umask()))

    def test_output_is_deterministic(self) -> None:
        a, _ = new_mod.build_plan(self.manifest, "sdl3-c", "demo", self.tmp / "a")
        b, _ = new_mod.build_plan(self.manifest, "sdl3-c", "demo", self.tmp / "b")
        self.assertEqual(a["files"], b["files"])
        a.pop("dest"), b.pop("dest")
        self.assertEqual(a, b)
        self.scaffold("sdl3-c", "demo", self.tmp / "a")
        self.scaffold("sdl3-c", "demo", self.tmp / "b")
        for entry in a["files"]:
            self.assertEqual((self.tmp / "a" / entry["path"]).read_bytes(),
                             (self.tmp / "b" / entry["path"]).read_bytes())

    def test_plan_hashes_match_written_files(self) -> None:
        import hashlib
        dest = self.tmp / "g"
        plan = self.scaffold("godot-2d", "demo", dest)
        for entry in plan["files"]:
            self.assertEqual(hashlib.sha256((dest / entry["path"]).read_bytes()).hexdigest(), entry["sha256"])

    def test_rejects_hostile_names(self) -> None:
        hostile = [
            "", "../x", "..", "/abs", "a/b", "a\\b", "-rf", "--help", ".hidden", "_lead", "1game", "a-",
            "Game", "my game", "x\n", "x\0", "name;rm", "$(id)", "a" * 49,
            "ｍygame",   # fullwidth m
            "my​game",  # zero-width space
            "café",     # accented letter
            "аpp",      # Cyrillic a
            "game∕x",   # division slash
        ]
        for name in hostile:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    new_mod.build_plan(self.manifest, "love2d", name, self.tmp / "dest")
                self.assertFalse((self.tmp / "dest").exists())

    def test_rejects_names_cargo_refuses(self) -> None:
        for name in ("test", "fn", "self", "async", "type", "crate"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "reserved"):
                    new_mod.validate_name(name)

    @unittest.skipUnless(shutil.which("cargo"), "cargo not installed")
    def test_accepted_names_are_valid_cargo_packages(self) -> None:
        for name in ("game", "my-game", "core", "tester", "fnord"):
            with self.subTest(name=name):
                dest = self.tmp / f"cargo-{name}"
                proc = subprocess.run(["cargo", "new", "--vcs", "none", "--offline", "-q", "--name", name, str(dest)],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                new_mod.validate_name(name)

    def test_accepts_reasonable_names(self) -> None:
        for name in ("a", "game", "my-game", "my_game2", "a" * 48):
            with self.subTest(name=name):
                self.assertEqual(new_mod.validate_name(name), name)

    def test_refuses_non_empty_destination(self) -> None:
        dest = self.tmp / "busy"
        dest.mkdir()
        (dest / "keep.txt").write_text("mine\n")
        with self.assertRaisesRegex(ValueError, "not empty"):
            new_mod.build_plan(self.manifest, "love2d", "demo", dest)
        self.assertEqual((dest / "keep.txt").read_text(), "mine\n")

    def test_refuses_file_destination(self) -> None:
        dest = self.tmp / "file"
        dest.write_text("x")
        with self.assertRaisesRegex(ValueError, "not a directory"):
            new_mod.build_plan(self.manifest, "love2d", "demo", dest)

    def test_accepts_existing_empty_directory(self) -> None:
        dest = self.tmp / "empty"
        dest.mkdir()
        self.scaffold("love2d", "demo", dest)
        self.assertTrue((dest / "main.lua").is_file())

    def test_refuses_symlinked_destination(self) -> None:
        real = self.tmp / "real"
        real.mkdir()
        link = self.tmp / "link"
        link.symlink_to(real)
        with self.assertRaisesRegex(ValueError, "symlink"):
            new_mod.build_plan(self.manifest, "love2d", "demo", link)
        with self.assertRaisesRegex(ValueError, "symlink"):
            new_mod.write_files(link, [("main.lua", b"x")])
        self.assertEqual(list(real.iterdir()), [])

    def test_refuses_dangling_symlink_destination(self) -> None:
        link = self.tmp / "dangling"
        link.symlink_to(self.tmp / "nowhere")
        with self.assertRaisesRegex(ValueError, "symlink"):
            new_mod.build_plan(self.manifest, "love2d", "demo", link)
        self.assertFalse((self.tmp / "nowhere").exists())

    def test_write_never_replaces_existing_file(self) -> None:
        dest = self.tmp / "race"
        dest.mkdir()
        (dest / "main.lua").write_text("mine\n")
        with self.assertRaises(FileExistsError):
            new_mod.write_files(dest, [("main.lua", b"theirs\n")])
        self.assertEqual((dest / "main.lua").read_text(), "mine\n")

    def test_write_refuses_symlinked_subdirectory(self) -> None:
        dest = self.tmp / "sub"
        dest.mkdir()
        outside = self.tmp / "outside"
        outside.mkdir()
        (dest / "src").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            new_mod.write_files(dest, [("src/main.c", b"int main(void){return 0;}\n")])
        self.assertEqual(list(outside.iterdir()), [])

    def test_refuses_destination_inside_templates(self) -> None:
        dest = new_mod.TEMPLATES_DIR / "love2d-copy-should-not-exist"
        with self.assertRaisesRegex(ValueError, "template tree"):
            new_mod.build_plan(self.manifest, "love2d", "demo", dest)
        self.assertFalse(dest.exists())

    def test_rejects_unknown_template(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown template"):
            new_mod.build_plan(self.manifest, "unreal", "demo", self.tmp / "x")

    def test_refuses_drifted_templates(self) -> None:
        tree = TemplateTree()
        self.addCleanup(tree.cleanup)
        (tree.root / "love2d" / "payload.sh").write_text("id\n")
        with self.assertRaises(ValueError):
            new_mod.load_manifest(tree.root)

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCAFFOLDER), *args], capture_output=True, text=True)

    def test_cli_happy_path_prints_json(self) -> None:
        dest = self.tmp / "cli"
        out = self.run_cli("--template", "raylib-c", "--name", "demo", "--dest", str(dest))
        self.assertEqual(out.returncode, 0, out.stderr)
        plan = json.loads(out.stdout)
        self.assertTrue(plan["written"])
        self.assertFalse(plan["executed"])
        self.assertEqual(plan["install_hint"], ["scripts/xodus-studio-plan.py", "--profile", "engines"])
        self.assertIn("demo", (dest / "CMakeLists.txt").read_text())

    def test_cli_dry_run_writes_nothing(self) -> None:
        dest = self.tmp / "dry"
        out = self.run_cli("--template", "sdl3-c", "--name", "demo", "--dest", str(dest), "--dry-run")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse(json.loads(out.stdout)["written"])
        self.assertFalse(dest.exists())

    def test_cli_bad_input_exits_2(self) -> None:
        busy = self.tmp / "busy"
        busy.mkdir()
        (busy / "f").write_text("x")
        cases = [
            ("--template", "love2d", "--name", "../x", "--dest", str(self.tmp / "n")),
            ("--template", "love2d", "--name=-rf", "--dest", str(self.tmp / "n")),
            ("--template", "nope", "--name", "demo", "--dest", str(self.tmp / "n")),
            ("--template", "love2d", "--name", "demo", "--dest", str(busy)),
            ("--template", "love2d", "--name", "demo"),
        ]
        for args in cases:
            with self.subTest(args=args):
                out = self.run_cli(*args)
                self.assertEqual(out.returncode, 2, out.stdout)
                self.assertEqual(out.stdout, "")
        self.assertFalse((self.tmp / "n").exists())

    def test_cli_list(self) -> None:
        out = self.run_cli("--list")
        self.assertEqual(out.returncode, 0)
        self.assertIn("godot-2d", out.stdout)

    def test_scaffolder_never_executes_or_networks(self) -> None:
        source = SCAFFOLDER.read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "os.exec", "os.spawn", "os.popen", "urllib", "socket",
                          "http.client", "shutil"):
            self.assertNotIn(forbidden, source)
        self.assertFalse(new_mod.network_used)
        self.assertFalse(new_mod.executes_commands)


def _umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current


def _find_tool(tool: str) -> str | None:
    found = shutil.which(tool)
    if found is None and (CARGO_HOME_BIN / tool).is_file():
        found = str(CARGO_HOME_BIN / tool)
    return found


def _smoke_test(template_id: str):
    def test(self: unittest.TestCase) -> None:
        manifest = new_mod.load_manifest()
        smoke = manifest["templates"][template_id]["smoke"]
        tools = {tool: _find_tool(tool) for tool in smoke["tools"]}
        reason = ""
        missing = sorted(t for t, path in tools.items() if path is None)
        if missing:
            reason = f"tool(s) not installed: {', '.join(missing)}"
        else:
            for module in smoke["pkg_config_modules"]:
                probe = subprocess.run([tools["pkg-config"], "--exists", module], capture_output=True)
                if probe.returncode != 0:
                    reason = f"pkg-config cannot find {module}"
                    break
        if reason:
            if REQUIRE_SMOKE:
                self.fail(f"{template_id} smoke build required but {reason}")
            self.skipTest(reason)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp, "smoke")
            plan, files = new_mod.build_plan(manifest, template_id, "smoke-game", dest)
            new_mod.write_files(dest, files)
            for step in plan["smoke"]["steps"]:
                argv = [tools[step[0]], *step[1:]]
                result = subprocess.run(argv, cwd=dest, capture_output=True, text=True, timeout=1800)
                self.assertEqual(result.returncode, 0,
                                 f"{' '.join(step)} failed:\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}")
    test.__doc__ = f"Scaffold {template_id} and run its manifest smoke steps."
    return test


class TemplateSmokeBuildTests(unittest.TestCase):
    """Real builds; each skips with a reason unless its toolchain is present."""


for _tid in load()["templates"]:
    setattr(TemplateSmokeBuildTests, f"test_smoke_{_tid.replace('-', '_')}", _smoke_test(_tid))


if __name__ == "__main__":
    unittest.main()

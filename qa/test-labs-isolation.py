#!/usr/bin/env python3
import importlib.util
import json
import os
import tempfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "labs_validator",
    Path(__file__).parents[1] / "scripts" / "xodus-labs-validate.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

BASE = {
    "schema_version": 1,
    "id": "001-test",
    "name": "Test Lab",
    "stage": "incubator",
    "enabled_by_default": False,
    "boot_dependency": False,
    "login_dependency": False,
    "installer_dependency": False,
    "recovery_dependency": False,
    "network_required": False,
    "permissions": [],
}


def fixture(overrides=None):
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name) / "labs"
    project = root / "001-test"
    project.mkdir(parents=True)
    data = dict(BASE)
    data.update(overrides or {})
    (project / "lab.json").write_text(json.dumps(data), encoding="utf-8")
    return temp, root


def expect_fail(overrides):
    temp, root = fixture(overrides)
    try:
        try:
            mod.validate_labs(root)
        except ValueError:
            return
        raise AssertionError(f"expected failure for {overrides}")
    finally:
        temp.cleanup()


def expect_root_fail(mutator):
    temp, root = fixture()
    try:
        mutator(root)
        try:
            mod.validate_labs(root)
        except ValueError:
            return
        raise AssertionError("expected Labs root validation failure")
    finally:
        temp.cleanup()


def main():
    temp, root = fixture()
    try:
        assert mod.validate_labs(root)[0]["id"] == "001-test"
    finally:
        temp.cleanup()

    for bad in (
        {"enabled_by_default": True},
        {"boot_dependency": True},
        {"login_dependency": True},
        {"installer_dependency": True},
        {"recovery_dependency": True},
        {"stage": "production-ish"},
        {"permissions": ["shell"] * 33},
        {"permissions": ["shell", "shell"]},
        {"id": "999-wrong"},
        {"unexpected_release_hook": True},
    ):
        expect_fail(bad)

    def non_object(root):
        (root / "001-test" / "lab.json").write_text("[]", encoding="utf-8")

    expect_root_fail(non_object)

    def symlink_manifest(root):
        project = root / "001-test"
        manifest = project / "lab.json"
        target = project / "real.json"
        target.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
        manifest.unlink()
        manifest.symlink_to(target.name)

    expect_root_fail(symlink_manifest)

    def symlink_project(root):
        project = root / "001-test"
        target = root / "real-project"
        project.rename(target)
        os.symlink(target.name, project, target_is_directory=True)

    expect_root_fail(symlink_project)

    def malformed_numbered_entry(root):
        (root / "002 Bad Name").mkdir()

    expect_root_fail(malformed_numbered_entry)

    def numbered_regular_file(root):
        (root / "002-file").write_text("not a project", encoding="utf-8")

    expect_root_fail(numbered_regular_file)

    print("PASS: strict AI Labs isolation contract")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

ALLOWED_STAGES = {"incubator", "experiment", "labs-beta", "xodus-feature"}
FORBIDDEN_DEPENDENCIES = (
    "boot_dependency",
    "login_dependency",
    "installer_dependency",
    "recovery_dependency",
)
REQUIRED_FIELDS = {
    "schema_version",
    "id",
    "name",
    "stage",
    "enabled_by_default",
    "boot_dependency",
    "login_dependency",
    "installer_dependency",
    "recovery_dependency",
    "network_required",
    "permissions",
}
ID_RE = re.compile(r"^[0-9]{3}-[a-z0-9][a-z0-9-]{1,47}$")


def fail(message: str) -> None:
    raise ValueError(message)


def validate_manifest(project_dir: Path) -> dict:
    if project_dir.is_symlink() or not project_dir.is_dir():
        fail(f"{project_dir.name}: project path must be a real directory")

    manifest_path = project_dir / "lab.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        fail(f"{project_dir.name}: lab.json missing or not a regular file")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"{project_dir.name}: invalid lab.json: {exc}")

    if not isinstance(data, dict):
        fail(f"{project_dir.name}: lab.json root must be an object")

    keys = set(data)
    missing = sorted(REQUIRED_FIELDS - keys)
    extra = sorted(keys - REQUIRED_FIELDS)
    if missing:
        fail(f"{project_dir.name}: missing fields: {', '.join(missing)}")
    if extra:
        fail(f"{project_dir.name}: unknown fields: {', '.join(extra)}")

    if data["schema_version"] != 1:
        fail(f"{project_dir.name}: unsupported schema_version")
    if data["id"] != project_dir.name or not ID_RE.fullmatch(data["id"]):
        fail(f"{project_dir.name}: invalid or mismatched id")
    if not isinstance(data["name"], str) or not data["name"].strip() or len(data["name"]) > 80:
        fail(f"{project_dir.name}: invalid name")
    if data["stage"] not in ALLOWED_STAGES:
        fail(f"{project_dir.name}: invalid stage")
    if data["enabled_by_default"] is not False:
        fail(f"{project_dir.name}: Labs projects must default disabled")
    for key in FORBIDDEN_DEPENDENCIES:
        if data[key] is not False:
            fail(f"{project_dir.name}: {key} must be false before graduation")
    if not isinstance(data["network_required"], bool):
        fail(f"{project_dir.name}: network_required must be boolean")

    permissions = data["permissions"]
    if not isinstance(permissions, list) or len(permissions) > 32:
        fail(f"{project_dir.name}: permissions must be a list of at most 32 entries")
    if any(not isinstance(p, str) or not p.strip() or len(p) > 64 for p in permissions):
        fail(f"{project_dir.name}: invalid permission entry")
    if len(set(permissions)) != len(permissions):
        fail(f"{project_dir.name}: duplicate permission entries")
    return data


def validate_labs(root: Path) -> list[dict]:
    if root.is_symlink() or not root.is_dir():
        fail("labs root missing or not a regular directory")

    numbered_entries = sorted(p for p in root.iterdir() if p.name[:1].isdigit())
    if not numbered_entries:
        fail("no Labs projects found")

    projects = []
    for entry in numbered_entries:
        if entry.is_symlink():
            fail(f"{entry.name}: numbered Labs project must not be a symlink")
        if not entry.is_dir():
            fail(f"{entry.name}: numbered Labs entry must be a directory")
        if not ID_RE.fullmatch(entry.name):
            fail(f"{entry.name}: invalid Labs project directory name")
        projects.append(entry)

    manifests = [validate_manifest(project) for project in projects]
    ids = [m["id"] for m in manifests]
    if len(ids) != len(set(ids)):
        fail("duplicate Labs project ids")
    return manifests


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Xodus AI Labs isolation manifests")
    parser.add_argument("--root", default="labs")
    args = parser.parse_args()
    try:
        manifests = validate_labs(Path(args.root))
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema_version": 1,
        "validated_projects": [m["id"] for m in manifests],
        "labs_isolated": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

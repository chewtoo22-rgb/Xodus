#!/usr/bin/env python3
"""Exercise Xodus dock staging against the exact reviewed package archive."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dock_identity", REPO / "overlay/identity/dock/apply-dock-identity.py")
dock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    lock = json.loads((dock.PAYLOAD / "source.lock.json").read_text())
    if dock.digest(args.package.read_bytes()) != lock["package_sha256"]:
        raise SystemExit("Dock archive differs from the reviewed package")
    members = [str(dock.CONTENTS / p) for p in lock["source_files"]]
    members += [str(dock.CONTENTS / "skins" / p) for p in lock["upstream_skin_files"]]
    with tempfile.TemporaryDirectory(prefix="xodus-dock-package-") as temporary:
        root = Path(temporary)
        subprocess.run(["tar", "--zstd", "-xf", str(args.package.resolve()), "-C", str(root), *members], check=True)
        config = root / dock.USER_CONFIGS[0]
        config.parent.mkdir(parents=True)
        config.write_text("[General]\nskinName=Tahoe Dark\niconSize=48\n")
        report = dock.apply(root, dock.PAYLOAD, lock)
        if config.read_text() != "[General]\nskinName=Xodus Dark\niconSize=48\n":
            raise SystemExit("Dock staging changed unrelated user preferences")
        if report != dock.verify(root):
            raise SystemExit("Dock retained report changed")
        print(json.dumps({"package": lock["package"], "version": lock["version"],
                          "package_sha256": lock["package_sha256"],
                          "verified_files": len(report["output_files"])}, sort_keys=True))


if __name__ == "__main__":
    main()

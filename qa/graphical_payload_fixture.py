"""Share disposable retained graphics with inventory and squashfs tests."""
from pathlib import Path
import shutil

import test_graphical_identity as graphical_fixture


def make_graphical_fixture(reference: Path, live_root: Path) -> None:
    fixture = graphical_fixture.RetainedGraphicalIdentityTests()
    fixture.setUp()
    try:
        shutil.copytree(fixture.reference, reference, dirs_exist_ok=True, symlinks=True)
        shutil.copytree(fixture.root, live_root, dirs_exist_ok=True, symlinks=True)
        checker = reference / 'qa/verify-graphical-identity.py'
        checker.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(__file__).parent / 'verify-graphical-identity.py', checker)
    finally:
        fixture.tearDown()

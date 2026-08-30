#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("x1_nuc_readiness_bundle", HERE / "x1-nuc-readiness-bundle.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

SHA = "a" * 40


def write_bundle(root: pathlib.Path, *, source="/dev/nvme0n1p2", fstype="ext4", boot="uefi", claim="not_automatic"):
    summary = root / "summary.txt"
    summary.write_text(
        "\n".join([
            "captured_at_utc=2026-08-30T12:00:00Z",
            "hostname=xodus-nuc",
            "kernel=6.12.0-xodus",
            f"root_source={source}",
            f"root_fstype={fstype}",
            f"boot_mode={boot}",
            "root_backing_disk=/dev/nvme0n1",
            "collector=pass",
            f"physical_install_claim={claim}",
            "",
        ]),
        encoding="utf-8",
    )
    first_boot = root / "first-boot.json"
    first_boot.write_text(json.dumps({
        "schema": 1,
        "status": "pass",
        "first_boot_completed_utc": "2026-08-30T11:59:00Z",
        "firmware": "uefi",
        "root_source": source,
        "root_fstype": fstype,
        "ai_tier": "standard",
        "ai_backend": "vulkan",
        "hardware_validation_claim": False,
    }), encoding="utf-8")
    return summary, first_boot


def expect_fail(summary, first_boot, sha=SHA):
    try:
        MODULE.validate(summary, first_boot, sha)
    except ValueError:
        return
    raise AssertionError("expected validation failure")


def test_pass():
    with tempfile.TemporaryDirectory() as td:
        summary, first_boot = write_bundle(pathlib.Path(td))
        result = MODULE.validate(summary, first_boot, SHA)
        assert result["status"] == "ready_for_nuc_hardware_test"
        assert result["candidate_sha"] == SHA
        assert result["hardware_validation_claim"] is False


def test_bios_rejected():
    with tempfile.TemporaryDirectory() as td:
        summary, first_boot = write_bundle(pathlib.Path(td), boot="bios")
        expect_fail(summary, first_boot)


def test_live_root_rejected():
    with tempfile.TemporaryDirectory() as td:
        summary, first_boot = write_bundle(pathlib.Path(td), source="airootfs", fstype="overlay")
        expect_fail(summary, first_boot)


def test_root_mismatch_rejected():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        summary, first_boot = write_bundle(root)
        data = json.loads(first_boot.read_text(encoding="utf-8"))
        data["root_source"] = "/dev/sda2"
        first_boot.write_text(json.dumps(data), encoding="utf-8")
        expect_fail(summary, first_boot)


def test_claim_guard_rejected():
    with tempfile.TemporaryDirectory() as td:
        summary, first_boot = write_bundle(pathlib.Path(td), claim="validated")
        expect_fail(summary, first_boot)


def test_first_boot_claim_rejected():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        summary, first_boot = write_bundle(root)
        data = json.loads(first_boot.read_text(encoding="utf-8"))
        data["hardware_validation_claim"] = True
        first_boot.write_text(json.dumps(data), encoding="utf-8")
        expect_fail(summary, first_boot)


def test_duplicate_summary_key_rejected():
    with tempfile.TemporaryDirectory() as td:
        summary, first_boot = write_bundle(pathlib.Path(td))
        with summary.open("a", encoding="utf-8") as handle:
            handle.write("collector=pass\n")
        expect_fail(summary, first_boot)


def test_bad_candidate_sha_rejected():
    with tempfile.TemporaryDirectory() as td:
        summary, first_boot = write_bundle(pathlib.Path(td))
        expect_fail(summary, first_boot, "abc123")


def test_symlink_input_rejected():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        summary, first_boot = write_bundle(root)
        linked = root / "linked-summary.txt"
        linked.symlink_to(summary)
        expect_fail(linked, first_boot)


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS {len(tests)} X1 NUC readiness bundle tests")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Disposable dock roots exercise package binding and retained artwork checks."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dock_identity", REPO / "overlay/identity/dock/apply-dock-identity.py")
dock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dock)


class DockIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "root"
        self.root.mkdir()
        self.lock = copy.deepcopy(json.loads((dock.PAYLOAD / "source.lock.json").read_text()))
        self.sources = {
            "ui/main.qml": '/* SPDX-License-Identifier: GPL-2.0-or-later */\n'
                           '      let skinName = Plasmoid.configuration.skinName || "Tahoe Dark";\n'
                           'function launchTask() { return taskModel.activate(); }\n',
            "ui/ConfigAppearance.qml": "import Qt.labs.folderlistmodel // Importante para listar las carpetas de skins\n"
                "        // ComboBox para mostrar los skins\n"
                "        QQC2.ComboBox { model: FolderListModel {} }\n"
                "        // --- Selector de Tamaño de Iconos ---\n"
                "        Slider { onMoved: backend.setIconSize(value) }\n",
            "config/main.xml": '<entry name="skinName"><default>Tahoe Dark</default></entry>\n',
        }
        self.lock["source_files"] = {p: dock.digest(t.encode()) for p, t in self.sources.items()}
        for relative, text in self.sources.items():
            self.write(dock.CONTENTS / relative, text.encode())
        for relative in self.lock["upstream_skin_files"]:
            data = ("Audited upstream fixture: " + relative).encode()
            self.lock["upstream_skin_files"][relative] = dock.digest(data)
            self.write(dock.CONTENTS / "skins" / relative, data)
        self.lock["patched_files"] = {p: dock.digest(b) for p, b in dock.patches(self.sources).items()}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def apply(self):
        return dock.apply(self.root, dock.PAYLOAD, self.lock)

    def test_stages_only_xodus_styles_preserving_backend_and_attribution(self):
        config = self.write(dock.USER_CONFIGS[0], b'[General]\nskinName=Tahoe\niconSize=46\nlaunchers=applications:org.kde.dolphin.desktop\n')
        report = self.apply()
        self.assertEqual(report, dock.verify(self.root, dock.PAYLOAD, self.lock))
        self.assertEqual(sorted(p.name for p in (self.root / dock.CONTENTS / "skins").iterdir()), sorted(dock.SKINS))
        self.assertIn("function launchTask() { return taskModel.activate(); }", (self.root / dock.CONTENTS / "ui/main.qml").read_text())
        self.assertIn("SPDX-License-Identifier: GPL-2.0-or-later", (self.root / dock.CONTENTS / "ui/main.qml").read_text())
        self.assertEqual(config.read_text(), '[General]\nskinName=Xodus Light\niconSize=46\nlaunchers=applications:org.kde.dolphin.desktop\n')
        self.assertEqual(set(report["output_files"]), set(dock.TRANSFER_FILES) - {dock.REPORT.as_posix()})

    def test_source_drift_stops_before_mutation(self):
        main = self.root / dock.CONTENTS / "ui/main.qml"
        main.write_bytes(main.read_bytes() + b"// changed\n")
        with self.assertRaisesRegex(SystemExit, "package input differs"):
            self.apply()
        self.assertTrue((self.root / dock.CONTENTS / "skins/Tahoe").is_dir())
        self.assertFalse((self.root / dock.REPORT).exists())

    def test_changed_upstream_artwork_stops_before_mutation(self):
        self.write(dock.CONTENTS / "skins/Tahoe/bg.png", b"different")
        with self.assertRaisesRegex(SystemExit, "package skin differs"):
            self.apply()
        self.assertEqual((self.root / dock.CONTENTS / "ui/main.qml").read_text(), self.sources["ui/main.qml"])

    def test_symlink_cannot_write_outside_root(self):
        outside = Path(self.temp.name) / "outside.qml"
        outside.write_text("host data")
        target = self.root / dock.CONTENTS / "ui/XodusSkinSelector.qml"
        target.symlink_to(outside)
        with self.assertRaisesRegex(SystemExit, "symlink"):
            self.apply()
        self.assertEqual(outside.read_text(), "host data")
        self.assertTrue((self.root / dock.CONTENTS / "skins/Tahoe").is_dir())

    def test_unknown_preference_stops_before_mutation(self):
        self.write(dock.USER_CONFIGS[0], b"skinName=Unreviewed Skin\n")
        with self.assertRaisesRegex(SystemExit, "Unreviewed"):
            self.apply()
        self.assertFalse((self.root / dock.REPORT).exists())

    def test_repo_crlf_checkout_has_identical_canonical_payload(self):
        overlay = Path(self.temp.name) / "windows-checkout"
        shutil.copytree(dock.PAYLOAD, overlay)
        for path in overlay.rglob("*"):
            if path.is_file() and path.suffix != ".png":
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertEqual(dock.asset_files(overlay), dock.asset_files(dock.PAYLOAD))

    def test_retained_checker_rejects_altered_art_even_if_manifest_updated(self):
        self.apply()
        path = self.write(dock.CONTENTS / "skins/Xodus Dark/frame.svg", b"altered")
        report_path = self.root / dock.REPORT
        report = json.loads(report_path.read_text())
        report["output_files"][path.relative_to(self.root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        report_path.write_text(json.dumps(report))
        with self.assertRaisesRegex(SystemExit, "reviewed contract"):
            dock.verify(self.root, dock.PAYLOAD, self.lock)

    def test_retained_checker_rejects_competing_skin(self):
        self.apply()
        (self.root / dock.CONTENTS / "skins/Tahoe").mkdir()
        with self.assertRaisesRegex(SystemExit, "competing"):
            dock.verify(self.root, dock.PAYLOAD, self.lock)

    def test_retained_checker_rejects_missing_asset_and_old_preference(self):
        self.apply()
        self.write(dock.USER_CONFIGS[1], b"skinName=Tahoe Dark\n")
        with self.assertRaisesRegex(SystemExit, "upstream skin preference"):
            dock.verify(self.root, dock.PAYLOAD, self.lock)
        self.write(dock.USER_CONFIGS[1], b"skinName=Xodus Dark\n")
        (self.root / dock.CONTENTS / "skins/Xodus Light/tasks.svg").unlink()
        with self.assertRaisesRegex(SystemExit, "payload differs"):
            dock.verify(self.root, dock.PAYLOAD, self.lock)


if __name__ == "__main__":
    unittest.main()

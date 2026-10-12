# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify that each Launchpad source upload carries its own desktop build target."""

import shutil
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from debian.deb822 import Deb822

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import release_artifacts


class ReleaseTargetTests(unittest.TestCase):
    def test_source_upload_metadata_matches_ubuntu_suite(self):
        for suite, target in (("noble", "gnome"), ("resolute", "desktops")):
            with self.subTest(suite=suite), tempfile.TemporaryDirectory() as directory:
                parent = Path(directory)
                source, output = parent / "source", parent / "release"
                (source / "debian").mkdir(parents=True)
                output.mkdir()
                for name in ("control", "changelog"):
                    shutil.copy2(ROOT / "debian" / name, source / "debian" / name)
                (source / "scripts").mkdir()
                for name in ("debian_target.py", "package_control.py"):
                    shutil.copy2(ROOT / "scripts" / name, source / "scripts" / name)
                version = "1.1.3-1ubuntu" + ("24.04.1" if suite == "noble" else "26.04.1")

                def run(*command, **kwargs):
                    if command[0] == "/usr/bin/python3":
                        subprocess.run(command, check=True, cwd=source)
                    if command[0] == "dpkg-buildpackage":
                        self.assertEqual((source / "debian/build-target").read_text().strip(), target)
                        fields = list(Deb822.iter_paragraphs((source / "debian/control").read_text()))
                        self.assertEqual("kwin-dev" in fields[0]["Build-Depends"], target == "desktops")
                        self.assertEqual("KDE Plasma" in fields[1]["Description"], target == "desktops")
                        self.assertIn(f"({version}) {suite};", (source / "debian/changelog").read_text())
                        (parent / f"ubuntu-dock-folders_{version}_source.changes").write_text("source fixture")

                with patch.object(release_artifacts, "run", side_effect=run):
                    upload = release_artifacts.build_source(source, {"suite": suite, "version": version},
                        output, {"signing_fingerprint": "test"}, {})
                self.assertEqual(upload["suite"], suite)
                self.assertTrue((output / upload["changes"]).is_file())

    def test_source_without_its_builder_is_not_rewritten_by_the_publisher(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            with patch.object(release_artifacts, "run") as run:
                with self.assertRaisesRegex(ValueError, "source must include"):
                    release_artifacts.configure_source(source, "resolute", "1.1.3-1ubuntu26.04.1", {})
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

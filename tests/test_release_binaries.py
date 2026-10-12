# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Reject unchecked, mismatched and altered release binaries."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apt_repo import sha256
import release_binaries
import release_publish


class ReleaseBinaryTests(unittest.TestCase):
    targets = [{"suite": "noble", "version": "9.8.7-1ubuntu24.04.1"},
               {"suite": "resolute", "version": "9.8.7-1ubuntu26.04.1"}]

    def bundles(self, root):
        for target in self.targets:
            directory = root / target["suite"]
            stage = directory / "stage/DEBIAN"
            stage.mkdir(parents=True)
            name = f"ubuntu-dock-folders_{target['version']}_amd64.deb"
            (stage / "control").write_text("Package: ubuntu-dock-folders\n"
                f"Version: {target['version']}\nArchitecture: amd64\n"
                "Maintainer: Example <test@example.invalid>\nDescription: Release fixture\n")
            package = directory / name
            subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(stage.parent), str(package)],
                           check=True, stdout=subprocess.DEVNULL)
            (directory / "binary.json").write_text(json.dumps(target | {
                "commit": "reviewed", "architecture": "amd64", "package": name,
                "files": {name: sha256(package)},
            }))

    def test_accepts_matching_packages_for_both_ubuntu_series(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bundles(root)
            self.assertEqual(set(release_binaries.checked(root, self.targets, "amd64", "reviewed")),
                             {"noble", "resolute"})

    def test_rejects_wrong_commit_missing_suite_or_changed_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bundles(root)
            with self.assertRaisesRegex(ValueError, "unexpected commit"):
                release_binaries.checked(root, self.targets, "amd64", "other")
            package = next((root / "resolute").glob("*.deb"))
            package.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release_binaries.checked(root, self.targets, "amd64", "reviewed")
            (root / "resolute/binary.json").unlink()
            with self.assertRaisesRegex(ValueError, "every supported"):
                release_binaries.checked(root, self.targets, "amd64", "reviewed")

    def test_apt_publishes_each_binary_into_its_own_suite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binaries = [target | {"file": target["suite"] + ".deb"} for target in self.targets]
            (root / "release.json").write_text(json.dumps({"binaries": binaries}))
            settings = {"apt_branch": "main", "apt_repository": "example/apt"}
            with (patch.object(release_publish, "apt_git_environment", return_value={}),
                  patch.object(release_publish, "run"),
                  patch.object(release_publish.subprocess, "run") as command,
                  patch.object(release_publish, "update_archive") as update):
                command.return_value.returncode = 0
                release_publish.publish_apt(root, settings, {})
                self.assertEqual([call.args[2]["suite"] for call in update.call_args_list],
                                 ["noble", "resolute"])
                self.assertEqual([call.args[0].name for call in update.call_args_list],
                                 ["noble.deb", "resolute.deb"])


if __name__ == "__main__":
    unittest.main()

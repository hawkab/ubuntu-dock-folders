# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Reject stale cores, incorrect ABI dependencies and mismatched Ubuntu payloads."""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from debian.deb822 import Deb822

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import debian_target
from desktop_dependencies import pin_versions, plugin_name
from desktop_payload import FRONTENDS, verify_builds
from package_control import combined


def core(directory, api=9):
    directory.mkdir(parents=True)
    (directory / "contract.json").write_text(json.dumps({"version": api}))
    (directory / "engine.js").write_text("export const version = " + str(api))
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}
    (directory / "manifest.json").write_text(json.dumps({"api": api, "files": files}))


class DesktopPackagingTests(unittest.TestCase):
    def test_corrupt_payload_is_rejected_even_when_all_manifests_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core(root / "core")
            for location in FRONTENDS:
                shutil.copytree(root / "core", root / location / "core")
            self.assertEqual(verify_builds(root), 9)
            (root / FRONTENDS[1] / "core/engine.js").write_text("corrupted")
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                verify_builds(root)

    def test_matching_stale_builds_are_rejected_against_current_source_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core(root / "core")
            for location in FRONTENDS:
                core(root / location / "core", 8)
            with self.assertRaisesRegex(RuntimeError, "current core"):
                verify_builds(root)

    def test_kwin_dependency_does_not_match_a_package_name_prefix(self):
        dependencies = "libkwin6-extra (>= 1), libkwin6 (>= 6.6), libkwin-x11-6 (>= 6.6), libc6 (>= 2.39)"
        self.assertEqual(pin_versions(dependencies, [("libkwin6", "4:6.6.6-1"), ("libkwin-x11-6", "4:6.6.4-1")]),
            "libkwin6-extra (>= 1), libkwin6 (= 4:6.6.6-1), libkwin-x11-6 (= 4:6.6.4-1), libc6 (>= 2.39)")

    def test_missing_or_ambiguous_kwin_dependency_is_rejected(self):
        for dependencies in ("libkwin6-extra (>= 1)", "libkwin6 (>= 6), libkwin6 (<< 7)"):
            with self.subTest(dependencies=dependencies), self.assertRaises(RuntimeError):
                pin_versions(dependencies, [("libkwin6", "4:6.6.6-1")])

    def test_invalid_companion_identity_cannot_escape_plugin_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("../other", "dockfoldersbackdrop_../other", ""):
                (root / "plugin-name.txt").write_text(name)
                with self.assertRaises(RuntimeError):
                    plugin_name(root)

    def test_control_update_preserves_unrelated_multiline_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "control"
            file.write_text("Package: ubuntu-dock-folders\nVersion: 1\nDepends: old\n"
                            "Description: Old description\n old text\n"
                            "X-Test: First line\n Second line\n")
            combined(file, "2", "libc6 (>= 2.39)")
            fields = Deb822(file.read_text())
            self.assertEqual(fields["X-Test"], "First line\n Second line")
            self.assertEqual(fields["Version"], "2")
            self.assertIn("GNOME, KDE Plasma and Xfce", fields["Description"])
            self.assertNotIn("old text", fields["Description"])


class DebianTargetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "debian").mkdir()
        (self.root / "packaging").mkdir()
        for name in ("debian/control", "debian/changelog", "packaging/release.toml"):
            shutil.copy2(ROOT / name, self.root / name)

    def fields(self):
        return list(Deb822.iter_paragraphs((self.root / "debian/control").read_text()))

    def test_resolute_source_includes_native_builds_and_desktop_payload(self):
        self.assertEqual(debian_target.configure(self.root, "resolute"), "desktops")
        source, binary = self.fields()
        for package in ("kwin-dev", "kwin-x11-dev", "libxfce4panel-2.0-dev", "labwc"):
            self.assertIn(package, source["Build-Depends"])
        self.assertIn("KDE Plasma and Xfce", binary["Description"])
        self.assertIn("ubuntu-dock-folders-xfce", binary["Provides"])
        self.assertEqual(debian_target.selected(self.root), "desktops")
        self.assertRegex((self.root / "debian/changelog").read_text(),
                         r"\([0-9.]+-1ubuntu26\.04\.1\) resolute;")

    def test_noble_source_stays_gnome_only_after_reconfiguring(self):
        debian_target.configure(self.root, "resolute")
        debian_target.configure(self.root, "noble")
        source, binary = self.fields()
        for package in ("kwin-dev", "kwin-x11-dev", "libxfce4panel-2.0-dev", "labwc"):
            self.assertNotIn(package, source["Build-Depends"])
        self.assertIn("gnome-shell (>= 46)", source["Build-Depends"])
        self.assertIn("gjs", source["Build-Depends"].split(",\n "))
        self.assertNotIn("Provides", binary)
        self.assertEqual(debian_target.selected(self.root), "gnome")

    def test_reconfiguring_same_suite_is_idempotent(self):
        for suite in ("noble", "resolute"):
            debian_target.configure(self.root, suite)
            expected = (self.root / "debian/control").read_bytes()
            debian_target.configure(self.root, suite)
            self.assertEqual((self.root / "debian/control").read_bytes(), expected)

    def test_unknown_suite_does_not_change_source_metadata(self):
        expected = (self.root / "debian/control").read_bytes()
        with self.assertRaises(ValueError):
            debian_target.configure(self.root, "unknown")
        self.assertEqual((self.root / "debian/control").read_bytes(), expected)

    def test_debhelper_dependencies_keep_other_substitutions(self):
        stage = self.root / "build/package/DEBIAN"
        stage.mkdir(parents=True)
        (stage / "control").write_text("Package: ubuntu-dock-folders\nDepends: libkwin6 (= 4:6.6.6-1), gjs\n")
        substvars = self.root / "debian/ubuntu-dock-folders.substvars"
        substvars.write_text("misc:Depends=\nshlibs:Depends=stale\nother=value\n")
        with patch.object(debian_target, "ROOT", self.root):
            debian_target.dependencies()
        self.assertEqual(substvars.read_text(),
            "misc:Depends=\nother=value\nshlibs:Depends=libkwin6 (= 4:6.6.6-1), gjs\n")


if __name__ == "__main__":
    unittest.main()

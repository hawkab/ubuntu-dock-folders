# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise actual dpkg removal and offline panel restoration without touching the desktop."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from plasma_recovery import recover, restore_panel


class PackageLifecycleTests(unittest.TestCase):
    def test_combined_package_replaces_separate_kwin_companions(self):
        if not shutil.which("fakeroot"):
            self.skipTest("fakeroot is needed for an isolated dpkg database")
        stage = ROOT / "build/package"
        if "ubuntu-dock-folders-kwin" not in (stage / "DEBIAN/control").read_text():
            self.skipTest("The GNOME-only build does not include KWin companions")
        with tempfile.TemporaryDirectory(prefix="dock-folders-upgrade-") as directory:
            artifacts = Path(directory)
            root = artifacts / "installed"
            package = artifacts / "combined.deb"
            subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(stage), str(package)],
                           check=True, capture_output=True, timeout=30)
            (root / "var/lib/dpkg").mkdir(parents=True)
            (root / "var/lib/dpkg/status").touch()
            (root / "var/log").mkdir()
            command = ["fakeroot", "dpkg", "--force-not-root", "--force-depends", "--force-script-chrootless",
                       "--root=" + str(root), "--log=" + str(root / "var/log/dpkg.log")]
            companions = []
            for suffix in ("", "-x11"):
                name = "ubuntu-dock-folders-kwin" + suffix
                legacy = artifacts / name
                namespace = "kwin-x11" if suffix else "kwin"
                effects = list((stage / "usr/lib").glob(f"*/qt6/plugins/{namespace}/effects/plugins/dockfoldersbackdrop_*.so"))
                self.assertEqual(len(effects), 1)
                target = legacy / effects[0].relative_to(stage)
                target.parent.mkdir(parents=True)
                shutil.copy2(effects[0], target)
                (legacy / "DEBIAN").mkdir()
                (legacy / "DEBIAN/control").write_text(
                    f"Package: {name}\nVersion: 1\nArchitecture: amd64\n"
                    "Maintainer: Example <test@example.invalid>\nDescription: Legacy companion fixture\n")
                candidate = artifacts / (name + ".deb")
                subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(legacy), str(candidate)],
                               check=True, capture_output=True, timeout=30)
                companions.append(name)
                subprocess.run([*command, "--install", str(candidate)], check=True, capture_output=True, timeout=30)
            effects = list((root / "usr/lib").rglob("dockfoldersbackdrop_*.so"))
            self.assertEqual(len(effects), 2)
            subprocess.run([*command, "--remove", *companions], check=True, capture_output=True, timeout=30)
            subprocess.run([*command, "--install", str(package)], check=True, capture_output=True, timeout=30)
            for effect in effects:
                self.assertTrue(effect.is_file())
                owners = subprocess.check_output(["dpkg-query", "--admindir=" + str(root / "var/lib/dpkg"),
                                                  "--search", "/" + str(effect.relative_to(root))], text=True)
                self.assertTrue(owners.startswith("ubuntu-dock-folders:"), owners)
            subprocess.run([*command, "--remove", "ubuntu-dock-folders"], check=True, capture_output=True, timeout=30)
            self.assertTrue(all(not effect.exists() for effect in effects))

    def test_dpkg_installs_and_removes_all_owned_files(self):
        if not shutil.which("fakeroot"):
            self.skipTest("fakeroot is needed for an isolated dpkg database")
        with tempfile.TemporaryDirectory(prefix="dock-folders-dpkg-") as directory:
            root = Path(directory)
            package = root / "staged.deb"
            stage = ROOT / "build/package"
            self.assertTrue((stage / "DEBIAN/control").is_file(), "The GNOME package stage is required; run make build")
            subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(stage), str(package)],
                           check=True, capture_output=True, timeout=30)
            (root / "var/lib/dpkg").mkdir(parents=True)
            (root / "var/lib/dpkg/status").touch()
            (root / "var/log").mkdir()
            command = ["fakeroot", "dpkg", "--force-not-root", "--force-depends", "--force-script-chrootless",
                       "--root=" + str(root), "--log=" + str(root / "var/log/dpkg.log")]
            subprocess.run([*command, "--install", str(package)], capture_output=True, text=True, check=True, timeout=30)
            installed = root / "usr/share/gnome-shell/extensions/dock-groups@local/extension.js"
            self.assertEqual(installed.read_bytes(), (ROOT / "extension/extension.js").read_bytes())
            self.assertTrue((root / "usr/share/ubuntu-dock-folders/scripts/package_lifecycle.py").exists())
            subprocess.run([*command, "--remove", "ubuntu-dock-folders"], capture_output=True, text=True, check=True, timeout=30)
            self.assertFalse(installed.exists())
            self.assertFalse((root / "usr/bin/ubuntu-dock-folders").exists())

    def test_offline_recovery_keeps_other_widgets_and_is_idempotent(self):
        record = {"panel": 2, "widget": 29, "original": {"id": 26, "type": "org.kde.plasma.icontasks",
                  "configuration": [{"path": ["General"], "values": {"launchers": "applications:test.desktop"}}]}}
        text = "[Containments][2][Applets][7]\nplugin=org.kde.plasma.systemtray\n\n"
        text += "[Containments][2][Applets][29]\nplugin=io.github.hawkab.DockFolders\n\n"
        text += "[Containments][2][Applets][29][Configuration][General]\nglass=true\n\n"
        text += "[Containments][2][General]\nAppletOrder=3;4;29;7;18\n"
        expected = restore_panel(text, record)
        self.assertIn("AppletOrder=3;4;26;7;18", expected)
        self.assertIn("plugin=org.kde.plasma.systemtray", expected)
        self.assertIn("launchers=applications:test.desktop", expected)
        self.assertNotIn("[Applets][29]", expected)
        self.assertEqual(restore_panel(expected, record), expected)
        with tempfile.TemporaryDirectory() as directory:
            config, state = Path(directory) / "panel", Path(directory) / "state"
            config.write_text(text)
            state.write_text(json.dumps(record))
            self.assertTrue(recover(config, state))
            self.assertFalse(recover(config, state))
            self.assertEqual(config.read_text(), expected)

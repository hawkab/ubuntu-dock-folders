# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check packaged session startup with the systemd XDG generator."""

import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from desktop_payload import install_dispatcher


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.generator = Path("/usr/lib/systemd/user-generators/systemd-xdg-autostart-generator")
        if not self.generator.exists():
            self.skipTest("The systemd XDG autostart generator is not installed")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stage = self.root / "stage"
        for directory in ("usr/share/ubuntu-dock-folders/scripts", "usr/share/applications", "usr/bin", "DEBIAN"):
            (self.stage / directory).mkdir(parents=True)
        (self.stage / "usr/share/applications/io.github.hawkab.UbuntuDockFolders.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Ubuntu Dock Folders\nExec=old\nCategories=Utility;\n")
        install_dispatcher(self.stage)
        self.desktop = self.stage / "etc/xdg/autostart/ubuntu-dock-folders.desktop"
        self.environment = dict(os.environ, HOME=str(self.root),
            XDG_CONFIG_HOME=str(self.root / "config"), XDG_CONFIG_DIRS=str(self.stage / "etc/xdg"),
            PATH=str(self.stage / "usr/bin") + os.pathsep + os.environ.get("PATH", ""))

    def generate(self):
        outputs = [self.root / name for name in ("normal", "early", "late")]
        for output in outputs:
            output.mkdir()
        subprocess.run([str(self.generator), *map(str, outputs)], env=self.environment,
                       check=True, capture_output=True, text=True)
        services = [file for output in outputs for file in output.glob("*.service")]
        return services

    def test_packaged_session_runs_on_every_supported_desktop(self):
        services = self.generate()
        self.assertEqual(len(services), 1)
        service = services[0]
        condition = next(line.removeprefix("ExecCondition=") for line in service.read_text().splitlines()
                         if line.startswith("ExecCondition="))
        for desktop in ("ubuntu:GNOME", "KDE", "XFCE"):
            with self.subTest(desktop=desktop):
                result = subprocess.run(shlex.split(condition),
                    env=self.environment | {"XDG_CURRENT_DESKTOP": desktop}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((service.parent / "xdg-desktop-autostart.target.wants" / service.name).is_symlink())

    def test_removed_executable_does_not_leave_a_failing_startup_service(self):
        executable = self.stage / "usr/bin/ubuntu-dock-folders"
        self.desktop.write_text(self.desktop.read_text().replace(
            "TryExec=ubuntu-dock-folders\n", f"TryExec={executable}\n"))
        executable.unlink()
        self.assertEqual(self.generate(), [])


if __name__ == "__main__":
    unittest.main()

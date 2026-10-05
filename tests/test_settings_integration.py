# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify live companion cleanup inside the real Ubuntu Settings panel."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class SettingsIntegrationTests(unittest.TestCase):
    def test_open_panel_survives_companion_removal(self):
        if not shutil.which("gnome-control-center"):
            self.skipTest("GNOME Settings is not installed")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            extension = home / "extension"
            shutil.copytree(ROOT / "build/extension", extension)
            probe = home / "probe.so"
            flags = subprocess.check_output(
                ["pkg-config", "--cflags", "--libs", "gio-2.0"], text=True,
            ).split()
            subprocess.run(
                ["cc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                 str(ROOT / "tests/settings_probe.c"), "-o", str(probe), *flags,
                 "-l:libgtk-4.so.1", "-ldl"], check=True,
            )
            env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
                       XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
                       XDG_CURRENT_DESKTOP="ubuntu:GNOME", DOCK_GROUPS_DATA=str(extension),
                       GSETTINGS_BACKEND="memory", GDK_BACKEND="x11", GSK_RENDERER="cairo",
                       GTK_A11Y="none", ADW_DISABLE_PORTAL="1", LANGUAGE="en", LC_ALL="en_US.UTF-8")
            env.pop("LD_PRELOAD", None)
            result = subprocess.run(
                ["dbus-run-session", "--", "/bin/sh", "-c",
                 'export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"; exec "$@"',
                 "settings-test", "env",
                 f"LD_PRELOAD={probe}:{ROOT / 'build/integration/settings-integration.so'}",
                 "gnome-control-center", "ubuntu"],
                env=env, capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DOCK_FOLDERS_SETTINGS_REMOVE_OK", result.stdout)
            self.assertFalse((extension / "preferences.ui").exists())


if __name__ == "__main__":
    unittest.main()

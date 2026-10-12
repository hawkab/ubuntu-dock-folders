# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check the real GNOME Extensions settings entry point with private settings."""

import os
import unittest
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from session_runner import run_isolated


class GnomePreferencesTests(unittest.TestCase):
    def test_native_entry_point_saves_common_controls(self):
        with tempfile.TemporaryDirectory(prefix="dock-folders-prefs-") as directory:
            home = Path(directory)
            env = dict(os.environ, HOME=directory, XDG_CONFIG_HOME=str(home/"config"),
                XDG_DATA_HOME=str(home/"data"), XDG_CACHE_HOME=str(home/"cache"), XDG_STATE_HOME=str(home/"state"),
                GSETTINGS_BACKEND="memory", LANGUAGE="en", LC_ALL="C.UTF-8", GIO_USE_VFS="local",
                GTK_A11Y="none", NO_AT_BRIDGE="1", GDK_BACKEND="x11", WAYLAND_DISPLAY="",
                XDG_CURRENT_DESKTOP="GNOME", GI_TYPELIB_PATH="/usr/lib/gnome-shell/girepository-1.0", LD_LIBRARY_PATH="/usr/lib/gnome-shell")
            output = run_isolated(["xvfb-run", "-a", "gjs", "-m", str(ROOT / "tests/preferences.js"), str(ROOT / "build/extension")], env, 15, capture=True)
            self.assertIn("GNOME preference entry point passed", output.stdout)
            self.assertNotIn("CRITICAL", output.stdout)
            self.assertNotIn("JS ERROR", output.stdout)

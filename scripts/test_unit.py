#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Run Python checks with a private home, display and supervised session bus."""

import os
import tempfile
from pathlib import Path
from session_runner import run_isolated

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory(prefix="dock-folders-unit-") as directory:
        home = Path(directory)
        env = dict(os.environ, HOME=directory, XDG_CONFIG_HOME=str(home/"config"),
            XDG_DATA_HOME=str(home/"data"), XDG_CACHE_HOME=str(home/"cache"), XDG_STATE_HOME=str(home/"state"),
            XDG_CURRENT_DESKTOP="GNOME", XDG_SESSION_TYPE="x11", GSETTINGS_BACKEND="memory", GIO_USE_VFS="local",
            LIBGL_ALWAYS_SOFTWARE="1", LP_NUM_THREADS="2",
            GTK_A11Y="none", GDK_BACKEND="x11", WAYLAND_DISPLAY="", NO_AT_BRIDGE="1")
        run_isolated(["xvfb-run", "-a", "/usr/bin/python3", "-m", "unittest", "discover", "-v",
                      "-s", str(ROOT/"tests"), "-p", "test_*.py"], env, 120)


if __name__ == "__main__":
    main()

#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise the installed Xfce plugin and its removal in a private X11 session."""

import os
import sys
import tempfile
from pathlib import Path
from session_runner import run_isolated

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory(prefix="dock-folders-native-xfce-") as directory:
        home = Path(directory)
        env = dict(os.environ, HOME=directory, XDG_CONFIG_HOME=str(home / "config"),
                   XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
                   XDG_STATE_HOME=str(home / "state"), GSETTINGS_BACKEND="keyfile",
                   XDG_CURRENT_DESKTOP="XFCE", XDG_SESSION_TYPE="x11", GDK_BACKEND="x11",
                   WAYLAND_DISPLAY="", LANGUAGE="en", LC_ALL="C.UTF-8", GIO_USE_VFS="local",
                   GTK_A11Y="none", NO_AT_BRIDGE="1")
        if "--source" in sys.argv:
            env["DOCK_FOLDERS_TEST_XFCE_SOURCE"] = str(ROOT / "build/xfce")
            env["XDG_DATA_DIRS"] = str(home / "prefix/usr/share") + ":/usr/local/share:/usr/share"
        command = ["xvfb-run", "-a", "-s", "-screen 0 1100x760x24", "/usr/bin/python3",
                   str(ROOT / "tests/xfce_panel_session.py")]
        run_isolated(command, env, 50)


if __name__ == "__main__":
    main()

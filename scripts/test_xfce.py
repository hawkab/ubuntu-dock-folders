#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Run the Xfce backend in an isolated X11 desktop without touching user settings."""

import os
import subprocess
import tempfile
from pathlib import Path
from session_runner import run_isolated

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory(prefix="dock-folders-xfce-") as directory:
        home = Path(directory)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
                   XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
                   XDG_STATE_HOME=str(home / "state"), GSETTINGS_BACKEND="memory",
                   XDG_CURRENT_DESKTOP="XFCE", XDG_SESSION_TYPE="x11",
                   DOCK_FOLDERS_EXTENSION=str(ROOT / "build/xfce/shared"),
                   LANGUAGE="en", LC_ALL="C.UTF-8", GTK_A11Y="none", GDK_BACKEND="x11",
                   WAYLAND_DISPLAY="", GIO_USE_VFS="local", NO_AT_BRIDGE="1")
        command = ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24",
                   "/usr/bin/python3", str(Path(__file__).resolve()), "--session"]
        run_isolated(command, env, 90)


def session():
    wm = subprocess.Popen(["xfwm4", "--compositor=on", "--replace"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        result = subprocess.run(["/usr/bin/python3", str(ROOT / "tests/xfce_session.py")],
                                capture_output=True, text=True, timeout=85)
        print(result.stdout, end="")
        print(result.stderr, end="", file=__import__("sys").stderr)
        result.check_returncode()
        if "Traceback" in result.stderr or "CRITICAL" in result.stderr:
            raise RuntimeError("Xfce session emitted a runtime error")
    finally:
        wm.terminate()
        wm.wait(timeout=5)


if __name__ == "__main__":
    import sys

    session() if "--session" in sys.argv else main()

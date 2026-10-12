#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise native folder controls in a private Xfce/Wayland panel."""

import os
import shlex
import sys
import tempfile
from pathlib import Path
from session_runner import run_isolated

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory(prefix="dock-folders-xfce-wayland-") as directory:
        home = Path(directory)
        config = home / "config/labwc"
        config.mkdir(parents=True)
        (config / "rc.xml").write_text("<labwc_config><desktops><number>1</number></desktops></labwc_config>")
        env = dict(os.environ, HOME=directory, XDG_CONFIG_HOME=str(home / "config"),
                   XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
                   XDG_STATE_HOME=str(home / "state"), GSETTINGS_BACKEND="keyfile",
                   XDG_CURRENT_DESKTOP="XFCE", XDG_SESSION_TYPE="wayland", GDK_BACKEND="wayland",
                   DISPLAY="", WAYLAND_DISPLAY="", WLR_BACKENDS="headless", WLR_RENDERER="pixman",
                   WLR_HEADLESS_OUTPUTS="1", GTK_A11Y="none", NO_AT_BRIDGE="1", GIO_USE_VFS="local",
                   LANGUAGE="en", LC_ALL="C.UTF-8", DOCK_FOLDERS_DEBUG="1")
        if "--installed" not in sys.argv:
            env["DOCK_FOLDERS_TEST_XFCE_SOURCE"] = str(ROOT / "build/xfce")
            env["XDG_DATA_DIRS"] = str(home / "prefix/usr/share") + ":/usr/local/share:/usr/share"
        command = shlex.join(["/usr/bin/python3", str(ROOT / "tests/xfce_wayland_session.py")])
        result = run_isolated(["labwc", "--config-dir", str(config), "--session", command], env, 90, capture=True)
        if not (home / "xfce-wayland.ok").exists():
            raise RuntimeError("Wayland panel check did not finish:\n" + result.stdout[-5000:])
        for line in result.stdout.splitlines():
            if "Xfce/Wayland:" in line:
                print(line)


if __name__ == "__main__":
    main()

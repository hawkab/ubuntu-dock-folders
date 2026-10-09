#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Run extension integration checks in an isolated, headless GNOME Shell."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
UUID = "dock-groups@local"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("wayland", "x11"), default="wayland")
    parser.add_argument("--client-backend", choices=("wayland", "x11"))
    parser.add_argument("--extension-dir", type=Path, help="Check an installed extension in the isolated session")
    options = parser.parse_args()
    client = options.client_backend or options.backend
    help_text = subprocess.check_output(["gnome-shell", "--help"], text=True)
    if options.backend == "x11" and "--x11 " not in help_text:
        parser.error("This GNOME Shell has no X11 session backend; use Wayland with Xwayland clients.")
    if options.backend == "x11" and client != "x11":
        parser.error("An X11 session requires X11 clients.")
    if options.backend == "x11" and not os.environ.get("DISPLAY"):
        parser.error("Run the X11 check with xvfb-run -a.")
    with tempfile.TemporaryDirectory(prefix="dock-folders-shell-") as directory:
        home = Path(directory)
        runtime = home / "runtime"
        runtime.mkdir(mode=0o700)
        data = home / "data"
        extension = data / "gnome-shell/extensions" / UUID
        if options.extension_dir:
            shutil.copytree(options.extension_dir, extension)
        else:
            with zipfile.ZipFile(ROOT / "dist" / f"{UUID}.shell-extension.zip") as archive:
                archive.extractall(extension)
        subprocess.run(["glib-compile-schemas", "--strict", str(extension / "schemas")], check=True)
        applications = data / "applications"
        applications.mkdir()
        for name in ("org.gnome.Shell.PerfHelper", "local.test.Second", "local.test.Third", "local.test.NoIcon"):
            (applications / f"{name}.desktop").write_text(
                "[Desktop Entry]\nType=Application\n"
                f"Name={name}\nExec=/bin/true\n"
                + ("Icon=utilities-terminal\n" if not name.endswith("NoIcon") else "")
                + ("StartupWMClass=Gnome-shell-perf-helper\n" if name.endswith("PerfHelper") else "")
            )
        config = home / "config/glib-2.0/settings"
        config.mkdir(parents=True)
        groups = {"stale": {
            "id": "local.groups.Stale", "name": "Stale", "icon": "folder-symbolic",
            "colors": ["#303030", "#505050"],
            "apps": [{"desktop": f"local.test.{name}.desktop", "label": name}
                     for name in ("Second", "Missing", "Third")],
        }}
        (config / "keyfile").write_text(
            "[org/gnome/shell]\n"
            f"enabled-extensions=['ubuntu-dock@ubuntu.com', '{UUID}']\n"
            "favorite-apps=['org.gnome.Shell.PerfHelper.desktop', 'local.groups.Stale.desktop']\n"
            "[org/gnome/shell/extensions/dock-groups]\n"
            "enabled=true\ninitialized=true\n"
            f"groups='{json.dumps(groups)}'\n"
            "[org/gnome/shell/extensions/dash-to-dock]\n"
            "dock-fixed=true\nautohide=false\nintellihide=false\nshow-trash=false\nshow-mounts=false\n"
        )
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_DATA_HOME=str(data), XDG_CONFIG_HOME=str(home / "config"),
                   XDG_CACHE_HOME=str(home / "cache"), GSETTINGS_BACKEND="keyfile",
                   LIBGL_ALWAYS_SOFTWARE="1", LP_NUM_THREADS="2", GTK_A11Y="none",
                   GDK_BACKEND=client, GSK_RENDERER="cairo", GDK_DEBUG="no-portals",
                   ADW_DISABLE_PORTAL="1", GIO_USE_VFS="local",
                   DOCK_FOLDERS_TEST_BACKEND=f"{options.backend}/{client}")
        env.pop("MUTTER_WM_CLASS_FILTER", None)
        for name in ("WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
            env.pop(name, None)
        if options.backend == "wayland":
            env.pop("DISPLAY", None)
            backend = ["--headless", "--virtual-monitor", "1280x720",
                       "--wayland-display", "dock-folders-test-display"]
            if client == "wayland" and "--no-x11" in help_text:
                backend.append("--no-x11")
        else:
            backend = ["--x11"]
        result = subprocess.run(
            ["dbus-run-session", "--", "/bin/sh", "-c",
             'export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"; exec "$@"',
             "shell-test", "gnome-shell", *backend, "--force-animations",
             "--automation-script", str(ROOT / "tests/shell.js")],
            env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
        )
        print(result.stdout, end="", flush=True)
        result.check_returncode()
        failures = ("Invalid value 'undefined' for property gicon", "Actor not in scroll view",
                    "clutter_actor_remove_child")
        if any(message in result.stdout for message in failures):
            raise RuntimeError("The compositor reported an invalid icon or detached dock actor")
        if "DOCK_FOLDERS_SHELL_OK " not in result.stdout:
            raise RuntimeError("The compositor did not complete its regression checks")


if __name__ == "__main__":
    main()

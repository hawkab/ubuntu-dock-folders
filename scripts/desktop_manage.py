#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Dispatch package commands to the current desktop and preserve manual disablement."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from gi.repository import GLib
from desktop_backend import select, preferences_path

SHARE = Path("/usr/share/ubuntu-dock-folders")


def migrate_launcher():
    """Route an owned legacy application entry through the desktop dispatcher."""
    path = Path(GLib.get_user_data_dir()) / "applications/io.github.hawkab.UbuntuDockFolders.desktop"
    if not path.exists():
        return
    text = path.read_text()
    command = next((line for line in text.splitlines() if line.startswith("Exec=")), "")
    if "dock-groups@local" not in command or not (
            "preferences.py" in command or "gnome-extensions prefs" in command):
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(re.sub(r"^Exec=.*$", "Exec=ubuntu-dock-folders preferences", text, flags=re.M))
    temporary.chmod(path.stat().st_mode & 0o777)
    temporary.replace(path)


def dispatch(backend, command, arguments):
    """Run the selected adapter without starting another desktop's services."""
    paths = {
        "gnome": SHARE / "scripts/manage.py",
        "plasma": SHARE / "plasma-management/plasma_manage.py",
        "xfce": SHARE / "xfce-management/xfce_manage.py",
    }
    if backend.desktop != "gnome":
        arguments = [argument for argument in arguments if argument != "--ubuntu-settings"]
    if command == "preferences" and backend.desktop != "plasma":
        environment = dict(os.environ, DOCK_FOLDERS_DESKTOP=backend.desktop)
        return subprocess.call(["/usr/bin/python3", str(preferences_path(backend.desktop)), "--global"], env=environment)
    script = paths[backend.desktop]
    if not script.is_file():
        raise RuntimeError(f"The {backend.desktop} adapter is not installed.")
    if backend.desktop == "plasma":
        command = {"enable": "install", "install": "install", "uninstall": "uninstall"}.get(command, command)
    elif backend.desktop == "xfce":
        command = {"install": "enable", "uninstall": "disable"}.get(command, command)
    return subprocess.call(["/usr/bin/python3", str(script), command, *arguments])


def sync_plasma_locales():
    """Refresh user catalogs from the selected Plasma widget without enabling it."""
    root = Path(GLib.get_user_data_dir()) / "plasma/plasmoids/io.github.hawkab.DockFolders"
    if not root.is_dir():
        return
    if not (root / "contents/locale").is_dir():
        return
    sys.path.insert(0, str(SHARE / "plasma-management"))
    import plasma_manage
    plasma_manage.install_locales(root)


def session(backend):
    """Initialize a desktop once; leave subsequent enable/disable choices alone."""
    migrate_launcher()
    if backend.desktop == "plasma":
        sync_plasma_locales()
    path = Path(GLib.get_user_data_dir()) / "launcher-groups/desktop-sessions.json"
    visited = json.loads(path.read_text()) if path.exists() else []
    if backend.desktop in visited:
        return 0
    existing = False
    arguments = []
    if backend.desktop == "xfce":
        sys.path.insert(0, str(SHARE / "xfce-management"))
        import xfce_manage
        values = xfce_manage.properties()
        existing = any(value.unpack() == "dockfolders" for key, value in values.items()
                       if key.startswith("/plugins/plugin-") and key.count("/") == 2)
        panels = xfce_manage.arrays(values)
        if panels:
            panel = max(panels, key=lambda key: values.get(key.removesuffix("/plugin-ids") + "/size",
                                                        GLib.Variant("u", 0)).unpack())
            arguments = ["--panel", panel.split("/")[2].removeprefix("panel-")]
    elif backend.desktop == "plasma":
        sys.path.insert(0, str(SHARE / "plasma-management"))
        import plasma_manage
        existing = any(widget["type"] == plasma_manage.ID for panel in plasma_manage.snapshot()
                       for widget in panel["widgets"])
    else:
        from gi.repository import Gio
        existing = "dock-groups@local" in Gio.Settings.new("org.gnome.shell").get_strv("enabled-extensions")
        arguments = ["--ubuntu-settings"]
    result = 0 if existing else dispatch(backend, "enable", arguments)
    if result == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(visited + [backend.desktop]) + "\n")
        temporary.chmod(0o600)
        temporary.replace(path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="preferences",
                        choices=("enable", "disable", "install", "uninstall", "preferences", "session", "status"))
    arguments, remainder = parser.parse_known_args()
    try:
        if os.geteuid() == 0 and arguments.command != "status":
            raise RuntimeError("Run this command as your desktop user, without sudo.")
        backend = select()
        if arguments.command == "status":
            print(backend.name)
            return 0
        return session(backend) if arguments.command == "session" else dispatch(backend, arguments.command, remainder)
    except (RuntimeError, ValueError, OSError, GLib.Error) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

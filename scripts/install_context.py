# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Resolve installation paths and perform desktop file operations."""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from backup import DATA, SYSTEM_EXTENSION, USER_EXTENSION, UUID
from gi.repository import Gio, GLib

__all__ = (
    "APP_ID", "APPLICATIONS", "DATA", "ROOT", "SERVICE", "STATE", "SYSTEM_EXTENSION", "USER_EXTENSION", "UUID",
    "atomic_copy", "quote_exec", "settings_file", "state", "write_state", "reload_settings_service",
    "shell_available", "refresh_desktop_database", "installed_extension",
)

ROOT = Path(__file__).resolve().parent.parent
APPLICATIONS = Path(GLib.get_user_data_dir()) / "applications"
SERVICE = Path(GLib.get_user_data_dir()) / "dbus-1/services/org.gnome.Settings.service"
STATE = DATA / "install-state.json"
APP_ID = "io.github.hawkab.UbuntuDockFolders"


def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix="." + destination.name, delete=False
    ) as temporary:
        path = Path(temporary.name)
    try:
        shutil.copy2(source, path)
        path.replace(destination)
    finally:
        path.unlink(missing_ok=True)


def quote_exec(value, field_codes=True):
    value = str(value)
    if field_codes:
        value = value.replace("%", "%%")
    quoted = '"' + re.sub(r'["`$\\]', lambda match: "\\" + match[0], value) + '"'
    return (
        quoted.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )


def settings_file(path):
    return (
        path == SERVICE
        or path.name == "org.gnome.Settings.desktop"
        or path.name.endswith("panel.desktop")
    )


def state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    result = {"desktop_backups": {}}
    legacy = DATA / "state.json"
    if legacy.exists():
        original = json.loads(legacy.read_text()).get("desktop_backups", {})
        result["desktop_backups"] = {
            name: contents for name, contents in original.items() if settings_file(Path(name))
        }
    return result


def write_state(value):
    DATA.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    STATE.chmod(0o600)


def reload_settings_service():
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "ReloadConfig", None, None, Gio.DBusCallFlags.NONE, 1000, None,
        )
    except GLib.Error:
        pass


def shell_available():
    try:
        result = Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "NameHasOwner", GLib.Variant("(s)", ("org.gnome.Shell",)),
            GLib.VariantType.new("(b)"), Gio.DBusCallFlags.NONE, 1000, None,
        )
        return result.unpack()[0]
    except GLib.Error:
        return False


def refresh_desktop_database():
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(APPLICATIONS)], check=True)


def installed_extension():
    if USER_EXTENSION.exists():
        return USER_EXTENSION
    if SYSTEM_EXTENSION.exists():
        return SYSTEM_EXTENSION
    raise RuntimeError("The extension is not installed.")

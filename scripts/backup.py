# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Snapshot user settings and managed files before installation."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from gi.repository import Gio, GLib

UUID = "dock-groups@local"
DATA = Path(GLib.get_user_data_dir()) / "launcher-groups"
USER_EXTENSION = Path(GLib.get_user_data_dir()) / "gnome-shell/extensions" / UUID
SYSTEM_EXTENSION = Path("/usr/share/gnome-shell/extensions") / UUID
SCHEMA = "org.gnome.shell.extensions.dock-groups"


def read_settings(extension):
    source = Gio.SettingsSchemaSource.new_from_directory(
        str(extension / "schemas"), Gio.SettingsSchemaSource.get_default(), False
    )
    return Gio.Settings.new_full(source.lookup(SCHEMA, False), None, None)


def backup(destination=None):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = (
        Path(destination)
        if destination
        else Path(GLib.get_user_state_dir()) / "ubuntu-dock-folders/backups" / stamp
    )
    destination.mkdir(parents=True, mode=0o700)
    shell = Gio.Settings.new("org.gnome.shell")
    snapshot = {
        "favorites": list(shell.get_strv("favorite-apps")),
        "enabled_extensions": list(shell.get_strv("enabled-extensions")),
        "disabled_extensions": list(shell.get_strv("disabled-extensions")),
        "files": [],
    }
    extension = USER_EXTENSION if USER_EXTENSION.exists() else SYSTEM_EXTENSION
    if (extension / "schemas/gschemas.compiled").exists():
        settings = read_settings(extension)
        snapshot["settings"] = {
            key: settings.get_value(key).print_(True)
            for key in (
                "enabled",
                "customization",
                "glass",
                "animation",
                "font-size",
                "groups",
                "initialized",
            )
        }
    for name, directory in (("data", DATA), ("extension", USER_EXTENSION)):
        if directory.exists():
            shutil.copytree(directory, destination / name)
    files = set(
        Path(GLib.get_user_data_dir()).joinpath("applications").glob("local.groups.*.desktop")
    )
    for state_name in ("state.json", "install-state.json"):
        state_path = DATA / state_name
        if state_path.exists():
            state = json.loads(state_path.read_text())
            files.update(Path(name) for name in state.get("created_files", []))
            files.update(Path(name) for name in state.get("desktop_backups", {}))
            files.update(Path(name) for name in state.get("presentation_backups", {}))
    for index, source in enumerate(sorted(files)):
        if source.is_file():
            copy = destination / "files" / str(index)
            copy.parent.mkdir(exist_ok=True)
            shutil.copy2(source, copy)
            snapshot["files"].append(
                {"original": str(source), "copy": str(copy.relative_to(destination))}
            )
    manifest = destination / "snapshot.json"
    manifest.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    manifest.chmod(0o600)
    return destination


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Snapshot user settings and managed files before installation."
    )
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    print(backup(args.destination))

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Settings and persistent folder data."""

import json
from pathlib import Path

from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parent.parent
APP_ID = "io.github.hawkab.UbuntuDockFolders"
DATA = Path(GLib.get_user_data_dir()) / "launcher-groups"
SCHEMA = "org.gnome.shell.extensions.dock-groups"
source = Gio.SettingsSchemaSource.new_from_directory(
    str(ROOT / "schemas"), Gio.SettingsSchemaSource.get_default(), False
)
schema = source.lookup(SCHEMA, False)
if schema is None:
    raise RuntimeError("Dock folders settings schema is missing")
SETTINGS = Gio.Settings.new_full(schema, None, None)


def groups():
    return json.loads(SETTINGS.get_string("groups"))

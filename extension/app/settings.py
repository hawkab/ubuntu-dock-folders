# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Settings and persistent folder data."""

import json
from pathlib import Path

from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(GLib.get_user_data_dir()) / "launcher-groups"
SCHEMA = "org.gnome.shell.extensions.dock-groups"
source = Gio.SettingsSchemaSource.new_from_directory(
    str(ROOT / "schemas"), Gio.SettingsSchemaSource.get_default(), False
)
SETTINGS = Gio.Settings.new_full(source.lookup(SCHEMA, False), None, None)


def groups():
    return json.loads(SETTINGS.get_string("groups"))

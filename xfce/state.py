# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Adapt Xfce settings and application metadata to the portable folder API."""

import json
import os
import sys
import uuid
from pathlib import Path
from gi.repository import Gio
from windows import desktop_info

SOURCE = Path(__file__).resolve().parent.parent
SHARED = Path(__file__).resolve().parent / "shared"
EXTENSION = Path(os.environ.get("DOCK_FOLDERS_EXTENSION", SHARED if SHARED.exists() else SOURCE / "extension"))
if not (EXTENSION / "schemas").exists():
    EXTENSION = Path("/usr/share/gnome-shell/extensions/dock-groups@local")
sys.path.insert(0, str(EXTENSION / "adapters"))
from runtime import CoreRuntime


class FolderState:
    """Persist command results and retain the core's single undo step."""

    def __init__(self):
        source = Gio.SettingsSchemaSource.new_from_directory(str(EXTENSION / "schemas"), Gio.SettingsSchemaSource.get_default(), False)
        schema = source.lookup("org.gnome.shell.extensions.dock-groups", False)
        if schema is None:
            raise RuntimeError("Dock folders settings schema is missing")
        self.settings = Gio.Settings.new_full(schema, None, None)
        self.core = CoreRuntime(EXTENSION)
        self.contract = self.core.call("contract")
        self.undo = None
        self.load()
        self.clean()

    def load(self):
        raw = self.settings.get_string("groups")
        favorites = list(self.settings.get_strv("xfce-favorites"))
        changed = favorites != getattr(self,"favorites",None)
        if raw != getattr(self,"groups_json",None):
            groups = json.loads(raw)
            changed |= self.core.call("folderChanges",{"previous":getattr(self,"groups",{}),"next":groups})["membership"]
            self.groups, self.groups_json = groups, raw
        self.favorites = favorites
        if changed or not hasattr(self,"grouped"):
            self.grouped = set(self.core.call("grouped", {"groups":self.groups,"favorites":self.favorites}))
        values = {item["name"]: self.settings.get_value(item["key"]).unpack() for item in self.contract["preferences"]}
        values["glass"] = self.settings.get_boolean("glass")
        if values != getattr(self,"raw_preferences",None):
            self.preferences = self.core.call("preferences", values)
            self.raw_preferences = values
        return changed

    def write(self):
        self.settings.delay()
        self.settings.set_string("groups", json.dumps(self.groups, ensure_ascii=False))
        self.settings.set_strv("xfce-favorites", self.favorites)
        self.settings.apply()

    def execute(self, command):
        state = {"groups":self.groups,"favorites":self.favorites,"undo":self.undo}
        ids = self.core.call("references", {"state":state,"command":command})
        entries = {}
        for desktop in ids:
            info = desktop_info(desktop)
            if info:
                entries[desktop] = {"desktop": desktop, "label": info.get_name()}
        result = self.core.call("transaction", {"state": {"groups": self.groups, "favorites": self.favorites, "undo": self.undo},
            "command": command, "entries": entries, "token": uuid.uuid4().hex[:12]})
        state = result["state"]
        self.groups, self.favorites, self.undo = state["groups"], state["favorites"], state.get("undo")
        if result["changed"]:
            self.grouped = set(self.core.call("grouped", {"groups":self.groups,"favorites":self.favorites}))
            self.write()
        return result["changed"]

    def clean(self):
        return self.execute({"operation": "reconcile"})

    def entry(self, desktop):
        for group in self.groups.values():
            for entry in group["apps"]:
                if entry["desktop"] == desktop:
                    return entry
        info = desktop_info(desktop)
        return {"desktop": desktop, "label": info.get_name()} if info else None

    def move(self, desktop, key, before=None):
        return self.execute({"operation": "move", "desktop": desktop, "key": key, "before": before})

    def create(self, desktop, target, name):
        return self.execute({"operation": "create", "desktop": desktop, "target": target, "name": name})

    def extract(self, desktop, before=None):
        return self.execute({"operation": "extract", "desktop": desktop, "before": before})

    def undo_last(self):
        return self.execute({"operation": "undo"})

    def close(self):
        self.core.close()

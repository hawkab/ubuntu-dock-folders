# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Adapt common folder selection and pin commands to desktop settings."""

import json
import uuid
from gi.repository import Gio
try:
    from .folder_sources import GnomeFolders, application_entries, settings
except ImportError:
    from folder_sources import GnomeFolders, application_entries, settings


class FolderLibrary:
    """List or pin folders using the supplied core call and desktop's favorites."""

    def __init__(self, store, desktop, call):
        self.store, self.desktop, self.call = store, desktop, call
        self.favorites_store = settings("org.gnome.shell") if desktop == "gnome" else store
        self.favorites_key = "favorite-apps" if desktop == "gnome" else desktop + "-favorites"
        self.sources = GnomeFolders()

    def favorites(self):
        return list(self.favorites_store.get_strv(self.favorites_key)) if self.favorites_store else []

    def catalog(self):
        return self.call("folderCatalog", {"groups":json.loads(self.store.get_string("groups")),
            "favorites":self.favorites(), "sources":self.sources.read(), "entries":application_entries()})

    def pin(self, id, pinned):
        if not self.favorites_store:
            return False
        catalog = self.catalog()
        command = self.call("folderCommand", {"catalog":catalog,"id":id,"pinned":pinned})
        if not command:
            return False
        groups = json.loads(self.store.get_string("groups"))
        entries = {id:{"desktop":id,"label":entry["label"]} for id,entry in application_entries().items()}
        result = self.call("transaction", {"state":{"groups":groups,"favorites":self.favorites(),"undo":None},
            "command":command, "entries":entries, "token":uuid.uuid4().hex[:12]})
        if not result["changed"]:
            return False
        state = result["state"]
        if state["groups"] != groups:
            self.store.set_string("groups", json.dumps(state["groups"],ensure_ascii=False))
        if state["favorites"] != self.favorites():
            self.favorites_store.set_strv(self.favorites_key,state["favorites"])
        for store in {self.store, self.favorites_store}:
            if store.get_has_unapplied():
                store.apply()
        Gio.Settings.sync()
        return True

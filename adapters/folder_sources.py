# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Read optional GNOME folder definitions and application metadata without GTK."""

from gi.repository import Gio, GLib


def settings(schema, path=None):
    source = Gio.SettingsSchemaSource.get_default()
    declaration = source.lookup(schema, True) if source else None
    return Gio.Settings.new_full(declaration, None, path) if declaration else None


def application_entries():
    entries = {}
    for info in Gio.AppInfo.get_all():
        desktop = info.get_id()
        if not desktop or desktop.startswith("local.groups."):
            continue
        entries[desktop] = {"desktop":desktop, "label":info.get_name(), "visible":info.should_show(),
            "categories":(getattr(info,"get_categories",lambda: "")() or "").split(";")}
    return entries


class GnomeFolders:
    """Read and watch app-grid sources when their schemas are installed."""

    def __init__(self):
        self.grid = settings("org.gnome.desktop.app-folders")
        self.signals, self.folders = [], {}
        self.changed = None

    def read(self):
        if not self.grid:
            return []
        children = self.grid.get_strv("folder-children")
        result = []
        for id in children:
            if not id or "/" in id:
                continue
            folder = settings("org.gnome.desktop.app-folders.folder", self.grid.props.path + "folders/" + id + "/")
            if not folder:
                continue
            name = folder.get_string("name")
            if folder.get_boolean("translate") and "/" not in name:
                for directory in GLib.get_system_data_dirs():
                    file = GLib.KeyFile()
                    try:
                        file.load_from_file(directory + "/desktop-directories/" + name, GLib.KeyFileFlags.NONE)
                        name = file.get_locale_string("Desktop Entry", "Name", None)
                        break
                    except GLib.Error:
                        continue
            result.append({"id":id, "name":name, "apps":list(folder.get_strv("apps")),
                "categories":list(folder.get_strv("categories")), "excludedApps":list(folder.get_strv("excluded-apps"))})
        return result

    def watch(self, changed):
        self.close()
        self.changed = changed
        if self.grid:
            self.signals.append((self.grid, self.grid.connect("changed::folder-children", self.rebind)))
            self.rebind()

    def rebind(self, *_args):
        for folder, signal in self.folders.values():
            folder.disconnect(signal)
        self.folders = {}
        for source in self.read():
            folder = settings("org.gnome.desktop.app-folders.folder", self.grid.props.path + "folders/" + source["id"] + "/")
            self.folders[source["id"]] = (folder, folder.connect("changed", lambda *_args: self.changed()))
        if self.changed:
            self.changed()

    def close(self):
        for object, signal in self.signals + list(self.folders.values()):
            object.disconnect(signal)
        self.signals, self.folders = [], {}
        self.changed = None

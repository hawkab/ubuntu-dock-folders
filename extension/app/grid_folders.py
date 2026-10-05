#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Pin existing GNOME app-grid folders without duplicating their settings."""

import json
import uuid

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk
from i18n import _, set_ui_direction
from settings import SETTINGS, groups

GRID = Gio.Settings.new("org.gnome.desktop.app-folders")
SHELL = Gio.Settings.new("org.gnome.shell")


def pinned_folders():
    favorites = set(SHELL.get_strv("favorite-apps"))
    return {
        group["gridFolder"]
        for group in groups().values()
        if group.get("gridFolder") and group["id"] + ".desktop" in favorites
    }


def read_folder(folder_id):
    if "/" in folder_id or folder_id not in GRID.get_strv("folder-children"):
        return None
    settings = Gio.Settings.new_with_path(
        "org.gnome.desktop.app-folders.folder", GRID.props.path + "folders/" + folder_id + "/"
    )
    name = settings.get_string("name")
    if settings.get_boolean("translate"):
        for directory in GLib.get_system_data_dirs():
            file = GLib.KeyFile()
            try:
                file.load_from_file(
                    directory + "/desktop-directories/" + name, GLib.KeyFileFlags.NONE
                )
                name = file.get_locale_string("Desktop Entry", "Name", None)
                break
            except GLib.Error:
                continue
    categories = set(settings.get_strv("categories"))
    infos = {
        app.get_id(): app
        for app in Gio.AppInfo.get_all()
        if app.should_show() and not app.get_id().startswith("local.groups.")
    }
    automatic = [
        id
        for id, app in infos.items()
        if categories.intersection((getattr(app, "get_categories", lambda: "")() or "").split(";"))
    ]
    excluded = settings.get_strv("excluded-apps")
    apps = [
        {"desktop": id, "label": infos[id].get_name()}
        for id in dict.fromkeys(settings.get_strv("apps") + automatic)
        if id in infos and id not in excluded
    ]
    return {"name": name, "apps": apps}


def pin_folder(folder_id):
    source = read_folder(folder_id)
    current = groups()
    if not source or not source["apps"]:
        return False
    favorites = list(SHELL.get_strv("favorite-apps"))
    linked = next((g for g in current.values() if g.get("gridFolder") == folder_id), None)
    if linked:
        desktop = linked["id"] + ".desktop"
        if desktop in favorites:
            return False
        members = {
            id for entry in linked["apps"] for id in [entry["desktop"], *entry.get("aliases", [])]
        }
        favorites = [id for id in favorites if id not in members]
        favorites.append(desktop)
        SHELL.set_strv("favorite-apps", list(dict.fromkeys(favorites)))
        Gio.Settings.sync()
        return True
    members = {entry["desktop"] for entry in source["apps"]}
    entries = {entry["desktop"]: entry for group in current.values() for entry in group["apps"]}
    for key, group in list(current.items()):
        group["apps"] = [entry for entry in group["apps"] if entry["desktop"] not in members]
        if len(group["apps"]) < 2 and not group.get("gridFolder"):
            id = group["id"] + ".desktop"
            if id in favorites:
                index = favorites.index(id)
                favorites[index : index + 1] = [entry["desktop"] for entry in group["apps"]]
            del current[key]
    suffix = uuid.uuid4().hex[:12]
    group_id = "local.groups.Folder_" + suffix
    current["folder-" + suffix] = {
        "id": group_id,
        "name": source["name"],
        "icon": "folder",
        "colors": ["#3584e4", "#62a0ea"],
        "gridFolder": folder_id,
        "apps": [entries.get(entry["desktop"], entry) for entry in source["apps"]],
    }
    SETTINGS.set_string("groups", json.dumps(current, ensure_ascii=False))
    aliases = members | {
        id
        for entry in source["apps"]
        for id in entries.get(entry["desktop"], entry).get("aliases", [])
    }
    favorites = [id for id in favorites if id not in aliases]
    favorites.append(group_id + ".desktop")
    SHELL.set_strv("favorite-apps", list(dict.fromkeys(favorites)))
    Gio.Settings.sync()
    return True


class GridFolders(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="local.groups.GridFolders", flags=Gio.ApplicationFlags.NON_UNIQUE
        )
        self.connect("activate", self.activate_window)

    def activate_window(self, _app):
        window = Adw.ApplicationWindow(
            application=self, title=_("App-grid folders"), default_width=540, default_height=460
        )
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        toolbar.set_content(page)
        window.set_content(toolbar)
        group = Adw.PreferencesGroup(
            title=_("Add an app-grid folder"),
            description=_("Keep folder names and applications in sync with GNOME's app grid"),
        )
        page.add(group)
        count = 0
        buttons = {}
        for id in GRID.get_strv("folder-children"):
            folder = read_folder(id)
            if not folder or not folder["apps"]:
                continue
            count += 1
            row = Adw.ActionRow(title=folder["name"])
            button = Gtk.Button(label=_("Pin to dock"), valign=Gtk.Align.CENTER)
            buttons[id] = button

            def clicked(button, folder_id=id):
                if pin_folder(folder_id):
                    refresh()

            button.connect("clicked", clicked)
            row.add_suffix(button)
            group.add(row)
        if not count:
            group.add(
                Adw.ActionRow(
                    title=_("No app-grid folders"), subtitle=_("Create a folder in Show Apps first")
                )
            )

        def refresh(*_args):
            pinned = pinned_folders()
            for folder_id, button in buttons.items():
                button.set_label(_("Pinned") if folder_id in pinned else _("Pin to dock"))
                button.set_sensitive(folder_id not in pinned)

        signals = [
            (SHELL, SHELL.connect("changed::favorite-apps", refresh)),
            (SETTINGS, SETTINGS.connect("changed::groups", refresh)),
        ]

        def closed(_window):
            for settings, signal in signals:
                settings.disconnect(signal)
            signals.clear()
            return False

        window.connect("close-request", closed)
        refresh()
        window.present()


if __name__ == "__main__":
    set_ui_direction()
    GridFolders().run()

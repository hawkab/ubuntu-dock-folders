#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Publish validated folder data to Plasma without running file I/O in plasmashell."""

import json
import shutil
import subprocess
from pathlib import Path

from gi.repository import Gio, GioUnix, GLib
from core_bridge import execute, invoke, close as close_core
from folder_library import FolderLibrary
from images import image_info, file_digest

BUS = "io.github.hawkab.DockFolders.Plasma"
PATH = "/io/github/hawkab/DockFolders"
SCHEMA = "org.gnome.shell.extensions.dock-groups"
CONTENTS = Path(__file__).resolve().parent.parent
XML = f"""<node><interface name="{BUS}">
  <property name="State" type="s" access="read"/>
  <property name="FolderRevision" type="u" access="read"/>
  <method name="ListFolders"><arg type="s" direction="out"/></method>
  <method name="PinFolder"><arg type="s" direction="in"/><arg type="b" direction="in"/><arg type="b" direction="out"/></method>
  <method name="Edit"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
  <method name="Import"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
  <method name="Wallpaper"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
  <method name="Launch"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
  <method name="Shutdown"><arg type="b" direction="out"/></method>
</interface></node>"""


def app_info(desktop):
    if not isinstance(desktop, str) or not desktop.endswith(".desktop") or "/" in desktop:
        return None
    try:
        return GioUnix.DesktopAppInfo.new(desktop)
    except (TypeError, GLib.Error):
        return None


class FolderService:
    """Coalesce settings and application catalog changes and retain one undo step."""

    def __init__(self, connection=None, shutdown=None):
        schemas = CONTENTS / "schemas"
        if not schemas.exists():
            schemas = Path(__file__).resolve().parents[3] / "build/extension/schemas"
        source = Gio.SettingsSchemaSource.new_from_directory(str(schemas), Gio.SettingsSchemaSource.get_default(), False)
        schema = source.lookup(SCHEMA, False)
        if schema is None:
            raise RuntimeError("Dock folders settings schema is missing")
        self.settings = Gio.Settings.new_full(schema, None, None)
        self.connection = connection
        self.shutdown = shutdown
        self.undo = None
        self.timer = 0
        self.last_state = ""
        self.folder_revision = 0
        self.catalog_dirty = False
        self.folder_catalog_dirty = True
        self.app_metadata = {}
        self.settings_signal = self.settings.connect("changed", self.queue)
        self.monitor = Gio.AppInfoMonitor.get()
        self.monitor_signal = self.monitor.connect("changed", self.queue)
        self.load()
        self.clean()
        self.library = FolderLibrary(self.settings,"plasma",invoke)
        self.library.sources.watch(self.queue)

    def load(self):
        raw = self.settings.get_string("groups")
        favorites = list(self.settings.get_strv("plasma-favorites"))
        changed = favorites != getattr(self,"favorites",None)
        self.folder_catalog_dirty |= changed
        if raw != getattr(self,"groups_json",None):
            groups = json.loads(raw)
            differences = invoke("folderChanges",{"previous":getattr(self,"groups",{}),"next":groups})
            changed |= differences["membership"]
            self.folder_catalog_dirty |= differences["membership"] or differences["launchers"]
            self.groups = groups
            self.groups_json = raw
        self.favorites = favorites
        return changed

    def write(self):
        self.groups_json = json.dumps(self.groups, ensure_ascii=False)
        self.settings.delay()
        self.settings.set_string("groups", self.groups_json)
        self.settings.set_strv("plasma-favorites", self.favorites)
        self.settings.apply()

    def transaction(self, request):
        result = execute(self.groups, self.favorites, self.undo, request, app_info)
        state = result["state"]
        self.groups, self.favorites, self.undo = state["groups"], state["favorites"], state.get("undo")
        return result["changed"]

    def clean(self):
        self.app_metadata.clear()
        changed = self.transaction({"operation": "reconcile"})
        if changed:
            self.folder_catalog_dirty = True
            self.write()
        return changed

    def queue(self, source=None, _key=None):
        if source is not None and source is getattr(self,"settings",None) and _key not in {"groups","plasma-favorites"}:
            return
        if source is getattr(self,"monitor",None) or source is None:
            self.catalog_dirty = True
            self.app_metadata = {}
        if source is not getattr(self,"settings",None):
            self.folder_catalog_dirty = True
        if not self.timer:
            self.timer = GLib.idle_add(self.flush)

    def flush(self):
        try:
            changed = self.load()
            if getattr(self,"catalog_dirty",True) or changed:
                self.clean()
                self.catalog_dirty = False
            state = self.state()
            if getattr(self,"folder_catalog_dirty",True):
                self.folder_revision += 1
                if self.connection:
                    self.connection.emit_signal(None, PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                        GLib.Variant("(sa{sv}as)", (BUS, {"FolderRevision": GLib.Variant("u", self.folder_revision)}, [])))
                self.folder_catalog_dirty = False
            if state != self.last_state:
                self.last_state = state
                if self.connection:
                    self.connection.emit_signal(None, PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                        GLib.Variant("(sa{sv}as)", (BUS, {"State": GLib.Variant("s", state)}, [])))
        finally:
            self.timer = 0
        return GLib.SOURCE_REMOVE

    def state(self):
        desktops = {item for item in self.favorites if not item.startswith("local.groups.")}
        desktops.update(entry["desktop"] for group in self.groups.values() for entry in group["apps"])
        apps = {}
        for desktop in desktops:
            if desktop in self.app_metadata:
                apps[desktop] = self.app_metadata[desktop]
                continue
            info = app_info(desktop)
            if info:
                icon = info.get_icon()
                icon_name = icon.get_names()[0] if isinstance(icon, Gio.ThemedIcon) else icon.to_string() if icon else "application-x-executable"
                apps[desktop] = {"desktop": desktop, "label": info.get_name(),
                                 "icon": icon_name}
                self.app_metadata[desktop] = apps[desktop]
        self.app_metadata = {desktop:value for desktop,value in self.app_metadata.items() if desktop in desktops}
        aliases = {alias: entry["desktop"] for group in self.groups.values() for entry in group["apps"]
                   for alias in entry.get("aliases", [])}
        return json.dumps({"groups": self.groups, "favorites": self.favorites, "apps": apps,
                           "aliases": aliases, "undo": self.undo is not None}, ensure_ascii=False)

    def edit(self, request):
        if not isinstance(request, dict):
            return False
        changed = self.transaction(request)
        if changed:
            if request.get("operation") not in {"appearance","applyAppearance"} or request.get("property") == "name":
                self.folder_catalog_dirty = True
            self.write()
        return changed

    def import_launchers(self, desktops):
        if self.settings.get_boolean("plasma-initialized"):
            return False
        grouped = {entry["desktop"]: group["id"] + ".desktop" for group in self.groups.values() for entry in group["apps"]}
        known = {group["id"] + ".desktop" for group in self.groups.values()}
        favorites = [grouped.get(desktop, desktop) for desktop in desktops if desktop in known or app_info(desktop)]
        favorites.extend(group["id"] + ".desktop" for group in self.groups.values())
        self.favorites = list(dict.fromkeys(favorites))
        self.settings.set_boolean("plasma-initialized", True)
        self.write()
        return True

    def wallpaper(self, key, uri):
        if key not in self.groups:
            return False
        if not uri:
            self.groups[key].update(wallpaper="", wallpaperName="")
        else:
            source = Gio.File.new_for_uri(uri).get_path()
            if not source or Path(source).stat().st_size > 20 * 1024 * 1024:
                return False
            if not image_info(source):
                return False
            directory = Path(GLib.get_user_data_dir()) / "launcher-groups/wallpapers"
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / (file_digest(source)[:20] + Path(source).suffix.lower())
            shutil.copyfile(source, target)
            self.groups[key].update(wallpaper=str(target), wallpaperName=Path(source).name)
        self.write()
        return True

    def method(self, _connection, _sender, _path, _interface, method, parameters, invocation):
        try:
            args = parameters.unpack()
            if method == "ListFolders":
                invocation.return_value(GLib.Variant("(s)", (json.dumps(self.library.catalog(),ensure_ascii=False),)))
                return
            if method == "PinFolder":
                success = self.library.pin(*args)
            elif method == "Edit":
                success = self.edit(json.loads(args[0]))
            elif method == "Import":
                success = self.import_launchers(json.loads(args[0]))
            elif method == "Wallpaper":
                success = self.wallpaper(*args)
            elif method == "Launch":
                info = app_info(args[0])
                success = info.launch([], None) if info else False
            elif method == "Shutdown":
                if self.shutdown:
                    GLib.idle_add(self.shutdown)
                success = True
            else:
                raise ValueError("Unknown method")
            invocation.return_value(GLib.Variant("(b)", (bool(success),)))
        except RuntimeError as error:
            invocation.return_dbus_error(BUS + ".CoreError", str(error))
        except (ValueError, KeyError, TypeError, OSError, GLib.Error, subprocess.SubprocessError) as error:
            invocation.return_dbus_error(BUS + ".InvalidRequest", str(error))

    def close(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        self.library.sources.close()
        self.settings.disconnect(self.settings_signal)
        self.monitor.disconnect(self.monitor_signal)
        close_core()


def main():
    loop = GLib.MainLoop()
    service = None

    def acquired(connection, _name):
        nonlocal service
        service = FolderService(connection, loop.quit)
        interface = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
        connection.register_object(PATH, interface, service.method,
                                   lambda _connection, _sender, _path, _interface, name: GLib.Variant("u", service.folder_revision) if name == "FolderRevision" else GLib.Variant("s", service.state()), None)

    owner = Gio.bus_own_name(Gio.BusType.SESSION, BUS, Gio.BusNameOwnerFlags.NONE,
                            acquired, None, lambda *_args: loop.quit())
    try:
        loop.run()
    finally:
        if service:
            service.close()
        Gio.bus_unown_name(owner)


if __name__ == "__main__":
    main()

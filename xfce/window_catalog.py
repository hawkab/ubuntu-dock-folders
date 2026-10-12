# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Resolve application IDs and coalesce events independently of the window backend."""

from gi.repository import Gio, GLib


class WindowCatalog:
    def __init__(self, changed):
        self.changed = changed
        self.records, self.catalog, self.groups, self.class_ids = {}, {}, {}, {}
        self.signals, self.timer = [], 0
        self.monitor = Gio.AppInfoMonitor.get()
        self.signals.append((self.monitor, self.monitor.connect("changed", self.installed_changed)))
        for name in ("window-opened", "window-closed", "active-window-changed"):
            self.signals.append((self.screen, self.screen.connect(name, self.queue)))
        self.refresh_catalog()
        self.refresh_windows()

    def installed_changed(self, *_args):
        self.refresh_catalog()
        self.changed(True)
        self.queue()

    def refresh_catalog(self):
        self.catalog = {info.get_id(): info for info in Gio.AppInfo.get_all()
                        if info.get_id() and not info.get_id().startswith("local.groups.")}
        self.index_classes()

    def index_classes(self):
        self.class_ids = {}
        for desktop, info in self.catalog.items():
            names = [desktop.removesuffix(".desktop"), info.get_name(), info.get_executable()]
            if hasattr(info, "get_startup_wm_class"):
                names.insert(0, info.get_startup_wm_class())
            for name in names:
                if name:
                    self.class_ids.setdefault(name.lower().rsplit("/", 1)[-1], desktop)
        for group in self.groups.values():
            for entry in group["apps"]:
                for name in entry.get("wmClasses", []):
                    self.class_ids[name.lower()] = entry["desktop"]
                for alias in entry.get("aliases", []):
                    self.class_ids[alias.removesuffix(".desktop").lower()] = entry["desktop"]

    def set_groups(self, groups):
        self.groups = groups
        signature = tuple((key,group["id"],tuple((entry["desktop"],tuple(entry.get("aliases",[])),
            tuple(entry.get("wmClasses",[]))) for entry in group["apps"])) for key,group in groups.items())
        if signature == getattr(self,"group_signature",None):
            return
        self.group_signature = signature
        self.index_classes()
        self.queue()

    def queue(self, *_args):
        if not self.timer:
            self.timer = GLib.timeout_add(40, self.flush)

    def flush(self):
        self.timer = 0
        self.refresh_windows()
        self.changed(False)
        return GLib.SOURCE_REMOVE

    def desktop(self, window):
        for name in (window.get_class_instance_name(), window.get_class_group_name()):
            if name and name.lower() in self.class_ids:
                return self.class_ids[name.lower()]
        group = window.get_class_group_name() or window.get_name()
        return "wm:" + group.lower()

    def close(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        for obj, signal in self.signals:
            obj.disconnect(signal)
        for window, signals in self.records.values():
            for signal in signals:
                window.disconnect(signal)
        self.records.clear()
        self.signals.clear()

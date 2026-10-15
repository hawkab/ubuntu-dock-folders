# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Adapt Xfce foreign toplevel events without using X11 window identifiers."""

import gi
import logging
gi.require_version("Libxfce4windowing", "0.0")
from gi.repository import Libxfce4windowing as Xfw
from window_catalog import WindowCatalog


class WaylandWindow:
    """Provide the controller's window operations through libxfce4windowing."""

    def __init__(self, window):
        self.window = window

    def __getattr__(self, name):
        return getattr(self.window, name)

    def get_class_instance_name(self):
        return next(iter(self.window.get_class_ids()), None)

    def get_class_group_name(self):
        application = self.window.get_application()
        return application.get_class_id() if application else None

    def get_icon(self):
        return self.window.get_icon(128, 1)

    def activate(self, timestamp):
        seats = self.window.get_screen().get_seats()
        if seats:
            self.window.activate(seats[0], timestamp)

    def activate_workspace(self, _timestamp):
        workspace = self.window.get_workspace()
        if workspace:
            workspace.activate()

    def minimize(self):
        self.window.set_minimized(True)


class WaylandTracker(WindowCatalog):
    def __init__(self, changed, core):
        self.screen = Xfw.Screen.get_default()
        super().__init__(changed, core)

    def refresh_windows(self):
        windows = {window: window for window in self.screen.get_windows()}
        for identity, (window, signals) in list(self.records.items()):
            if identity not in windows:
                for signal in signals:
                    window.window.disconnect(signal)
                self.records.pop(identity)
        for identity, window in windows.items():
            if identity not in self.records:
                signals = [window.connect(name, self.queue) for name in
                           ("state-changed", "class-changed", "name-changed", "icon-changed")]
                self.records[identity] = (WaylandWindow(window), signals)

    def desktop(self, window):
        pwa = self.pwa_desktop(window.window.get_class_ids())
        if pwa is not None:
            return pwa
        for name in window.window.get_class_ids():
            if name and name.removesuffix(".desktop").lower() in self.class_ids:
                return self.class_ids[name.removesuffix(".desktop").lower()]
        desktop = super().desktop(window)
        logging.getLogger("ubuntu-dock-folders.xfce").debug("Wayland classes=%s application=%s desktop=%s",
            window.window.get_class_ids(), window.get_class_group_name(), desktop)
        return desktop

    def by_app(self):
        apps = {}
        for window, _signals in self.records.values():
            if window.is_skip_tasklist():
                continue
            apps.setdefault(self.desktop(window), []).append(window)
        return apps

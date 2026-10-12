# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Track X11 windows and expose the shared application catalog."""

import gi
gi.require_version("Wnck", "3.0")
from gi.repository import Wnck
from window_catalog import WindowCatalog


class X11Tracker(WindowCatalog):
    def __init__(self, changed):
        Wnck.set_client_type(Wnck.ClientType.PAGER)
        self.screen = Wnck.Screen.get_default()
        self.screen.force_update()
        super().__init__(changed)

    def refresh_windows(self):
        windows = {window.get_xid(): window for window in self.screen.get_windows()}
        for xid, (window, signals) in list(self.records.items()):
            if xid not in windows:
                for signal in signals:
                    window.disconnect(signal)
                self.records.pop(xid)
        for xid, window in windows.items():
            if xid in self.records:
                continue
            signals = [window.connect(name, self.queue) for name in
                       ("state-changed", "class-changed", "name-changed", "icon-changed")]
            self.records[xid] = (window, signals)

    def by_app(self):
        apps = {}
        for window, _signals in self.records.values():
            if (window.is_skip_tasklist() or window.get_window_type() not in
                    (Wnck.WindowType.NORMAL, Wnck.WindowType.DIALOG)):
                continue
            apps.setdefault(self.desktop(window), []).append(window)
        return apps

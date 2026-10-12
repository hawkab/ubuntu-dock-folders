# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Open global or per-folder GTK preferences."""

import sys
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk
from settings import APP_ID, ROOT, SETTINGS, groups
from i18n import set_ui_direction
from global_preferences import build_global_window
from window_lifecycle import on_window_close
from folder_appearance import FolderAppearance
from folder_wallpaper import FolderWallpaper, wallpaper_filters

__all__ = ("Preferences", "ROOT", "SETTINGS", "groups", "wallpaper_filters")

class Preferences(Adw.Application, FolderAppearance, FolderWallpaper):
    """Run preferences for a folder key, or global preferences for None."""
    def __init__(self, key, tab="dock"):
        super().__init__(
            application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE
        )
        if GLib.get_application_name() != "Ubuntu Dock Folders":
            GLib.set_application_name("Ubuntu Dock Folders")
        Gtk.Window.set_default_icon_name(APP_ID)
        self.key, self.tab = key, tab
        self.connect("activate", self.activate_window)


    def activate_window(self, _app):
        if self.key is None:
            window = build_global_window(self.tab)
        else:
            group = groups().get(self.key)
            if group is None:
                self.quit()
                return
            window = self.group_window(group)
            changed = SETTINGS.connect(
                "changed::blur-strength", lambda _settings, _key: self.refresh_previews(groups()[self.key])
            )
            on_window_close(window, lambda _window: SETTINGS.disconnect(changed))
        window.set_application(self)
        window.present()


if __name__ == "__main__":
    key = None if len(sys.argv) < 2 or sys.argv[1] == "--global" else sys.argv[1]
    set_ui_direction()
    Preferences(key).run([sys.argv[0]])

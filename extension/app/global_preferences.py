# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Build the same general preferences for standalone and Ubuntu Settings windows."""

import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk
from settings import ROOT, SETTINGS
from i18n import DOMAIN, set_ui_direction
from preferences_binding import bind_preferences
from settings_preview import attach_previews
from existing_folders import attach_existing_folders


def build_global_window(tab="dock", desktop=None):
    """Return a bound window with three tabs and live shared-core previews."""
    desktop = desktop or ("xfce" if os.environ.get("DOCK_FOLDERS_DESKTOP") == "xfce"
        or "xfce" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower() else "gnome")
    builder = Gtk.Builder()
    builder.set_translation_domain(DOMAIN)
    builder.add_from_file(str(ROOT / "preferences.ui"))
    window = builder.get_object("preferences_window")
    bind_preferences(builder, SETTINGS, window)
    core = attach_previews(builder, SETTINGS, window, desktop)
    attach_existing_folders(builder, SETTINGS, window, desktop, core)
    builder.get_object("settings_stack").set_visible_child_name(tab)
    return window


def open_embedded(parent):
    """Return a native modal owned by the running Ubuntu Settings application."""
    set_ui_direction()
    window = build_global_window(desktop="gnome")
    window.set_application(parent.get_application())
    window.set_transient_for(parent)
    window.set_destroy_with_parent(True)
    window.set_modal(True)
    return window

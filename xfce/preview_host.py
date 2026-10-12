# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Create a standalone Wayland panel for source previews."""

import gi
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell


def create(size, orientation):
    window = Gtk.Window(title="Dock folders")
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, "ubuntu-dock-folders-preview-panel")
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.TOP)
    GtkLayerShell.set_exclusive_zone(window, size)
    edge = GtkLayerShell.Edge.BOTTOM if orientation == 0 else GtkLayerShell.Edge.LEFT
    GtkLayerShell.set_anchor(window, edge, True)
    return window

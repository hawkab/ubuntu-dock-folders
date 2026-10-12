# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Position a native window chooser above its panel or folder anchor."""

import gi
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, Gtk, GtkLayerShell
from wayland_popup import panel_origin


def create(controller):
    window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, "ubuntu-dock-folders-preview")
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_exclusive_zone(window, 0)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)
    monitor = GtkLayerShell.get_monitor(controller.window)
    if monitor:
        GtkLayerShell.set_monitor(window, monitor)
    for edge in (GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.TOP):
        GtkLayerShell.set_anchor(window, edge, True)
    return window


def place(window, anchor):
    parent = anchor.get_toplevel()
    monitor = GtkLayerShell.get_monitor(parent) or Gdk.Display.get_default().get_monitor(0)
    area = monitor.get_geometry()
    x, y = anchor.translate_coordinates(parent, 0, 0)
    left, top = panel_origin(parent)
    _minimum, natural = window.get_preferred_size()
    width, height = natural.width, natural.height
    x = max(area.x+6, min(left+x, area.x+area.width-width-6))
    y += top
    y = y-height-6 if y > area.y+area.height/2 else y+anchor.get_allocated_height()+6
    y = max(area.y+6, min(y, area.y+area.height-height-6))
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.LEFT, x-area.x)
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, y-area.y)

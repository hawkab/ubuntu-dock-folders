# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Present a native application and a high-contrast backdrop in a private session."""

import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk


def draw(_area, context):
    width, height = _area.get_allocated_width(), _area.get_allocated_height()
    context.set_source_rgb(1,1,1)
    context.paint()
    context.set_source_rgb(0,0,0)
    for x in range(0,width,16):
        context.rectangle(x,0,8,height)
    context.fill()
    return False


def activate(application):
    window = Gtk.ApplicationWindow(application=application, title="Native Wayland test window")
    area = Gtk.DrawingArea()
    area.connect("draw", draw)
    window.add(area)
    window.maximize()
    window.show_all()


if __name__ == "__main__":
    if not os.environ.get("DOCK_FOLDERS_TEST_SESSION"):
        raise SystemExit("Private test session required.")
    GLib.set_prgname("test.terminal")
    Gdk.set_program_class("test.terminal")
    application = Gtk.Application(application_id="test.terminal")
    application.connect("activate", activate)
    application.run(None)

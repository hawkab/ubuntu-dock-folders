# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Select the window adapter from the actual display and resolve desktop launchers."""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib
try:
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix
except (ImportError, ValueError):
    GioUnix = Gio


def desktop_info(desktop):
    try:
        return GioUnix.DesktopAppInfo.new(desktop)
    except (TypeError, GLib.Error):
        return None


def WindowTracker(changed, core):
    """Return a tracker for the actual display, including Xwayland applications."""
    if Gdk.Display.get_default().__gtype__.name == "GdkWaylandDisplay":
        from wayland_windows import WaylandTracker
        return WaylandTracker(changed, core)
    from x11_windows import X11Tracker
    return X11Tracker(changed, core)

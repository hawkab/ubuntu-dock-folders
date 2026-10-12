# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Anchor a native xdg-popup to its panel and handle compositor dismissal."""

import time
import logging
import gi
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell
from folder_popup import FolderPopup
logger = logging.getLogger("ubuntu-dock-folders.xfce")


def panel_origin(window):
    """Return the layer panel's logical output origin, including panel margins."""
    monitor = GtkLayerShell.get_monitor(window) or Gdk.Display.get_default().get_monitor(0)
    area = monitor.get_geometry()
    width, height = window.get_allocated_width(), window.get_allocated_height()
    coordinates = []
    for start, end, offset, length, size in (
            (GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT, area.x, area.width, width),
            (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, area.y, area.height, height)):
        if GtkLayerShell.get_anchor(window, start):
            coordinates.append(offset + GtkLayerShell.get_margin(window, start))
        elif GtkLayerShell.get_anchor(window, end):
            coordinates.append(offset + length - size - GtkLayerShell.get_margin(window, end))
        else:
            coordinates.append(offset + (length - size) // 2)
    return tuple(coordinates)


class WaylandPopup(FolderPopup):
    def __init__(self, controller, key, anchor):
        window = Gtk.Window(type=Gtk.WindowType.POPUP)
        window.set_transient_for(controller.window)
        super().__init__(controller, key, anchor, window)
        self.opened = time.monotonic()
        window.connect("grab-broken-event", self.grab_broken)
        window.connect("unmap", self.unmapped)

    def anchor_rect(self):
        x, y = self.anchor.translate_coordinates(self.controller.window, 0, 0)
        left, top = panel_origin(self.controller.window)
        return left+x, top+y, self.anchor.get_allocated_width(), self.anchor.get_allocated_height()

    def position_window(self, left, top, width, height):
        self.window.resize(width, height)
        self.window.realize()
        px, py = panel_origin(self.controller.window)
        rectangle = Gdk.Rectangle()
        rectangle.x, rectangle.y = left-px, top-py
        rectangle.width, rectangle.height = width, height
        self.window.get_window().move_to_rect(rectangle, Gdk.Gravity.NORTH_WEST,
            Gdk.Gravity.NORTH_WEST, Gdk.AnchorHints.SLIDE_X | Gdk.AnchorHints.SLIDE_Y, 0, 0)

    def show(self):
        self.open_event = Gtk.get_current_event()
        self.controller.folder_tooltips(False)
        self.content.show_all()
        self.render()
        self.place()
        self.capture_background(self.rect["width"], self.rect["height"],self.show_prepared)

    def show_prepared(self):
        self.content.set_opacity(0)
        self.seat = Gdk.Display.get_default().get_default_seat()
        self.grabbed = self.seat.grab(self.window.get_window(), Gdk.SeatCapabilities.ALL,
            True, None, self.open_event, lambda *_args: self.window.show_all(), None) == Gdk.GrabStatus.SUCCESS
        logger.debug("Popup %s: mapped with grab=%s", self.key, self.grabbed)
        if not self.grabbed:
            self.close(False)
            return
        self.window.grab_add()
        deadline = time.monotonic()+1
        def start():
            if self.controller.popup is not self:
                return GLib.SOURCE_REMOVE
            if time.monotonic() > deadline:
                self.close(False)
                return GLib.SOURCE_REMOVE
            if not self.window.get_mapped() or self.content.get_allocated_width() <= 1:
                return GLib.SOURCE_CONTINUE
            self.window.check_resize()
            self.loading = False
            self.update_input_region()
            self.animate(False)
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(16, start)

    def grab_broken(self, *_args):
        logger.debug("Popup %s: grab broken, dragging=%s", self.key, self.controller.dragging)
        if self.controller.popup is self and not self.closing and not self.controller.dragging:
            self.close(False)
        return False

    def unmapped(self, *_args):
        if self.controller.popup is self and not self.closing:
            self.close(False)

    def focus_lost(self, *_args):
        return False

    def outside(self, _window, event):
        widget = Gtk.get_event_widget(event)
        logger.debug("Popup %s: press widget=%s xy=%s root=%s", self.key,
            widget.__gtype__.name if widget else None, (event.x,event.y), (event.x_root,event.y_root))
        pointer = self.seat.get_pointer() or event.get_device()
        source, px, py = pointer.get_window_at_position() if pointer else (None, event.x, event.y)
        logger.debug("Popup %s: pointer focus=%s parent=%s xy=%s", self.key,
                     source, self.controller.window.get_window(), (px,py))
        if source and source.get_toplevel() == self.controller.window.get_window():
            origin = source.get_origin()[-2:]
            self.controller.folder_press({"x": origin[0]+px, "y": origin[1]+py})
            return True
        if widget and widget is not self.window and widget.is_ancestor(self.window):
            return False
        if widget is self.window and (self.rect["x"] <= event.x < self.rect["x"]+self.rect["width"]
                and self.rect["y"] <= event.y < self.rect["y"]+self.rect["height"]):
            return False
        if self.controller.dragging:
            return False
        if event.button == 1:
            self.controller.folder_press({"x": event.x_root, "y": event.y_root})
        else:
            self.close()
        return True

    def close(self, animate=True):
        logger.debug("Popup %s: close animate=%s closing=%s", self.key, animate, self.closing)
        super().close(animate)

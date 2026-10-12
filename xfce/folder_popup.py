#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Keep an anchored folder window alive across content changes."""



import gi
import cairo
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango
from state import EXTENSION
import sys
sys.path.insert(0, str(EXTENSION / "app"))
from i18n import _

from animation import PopupAnimation
from surface import PopupSurface
from placement import PopupPlacement


class FolderPopup(PopupAnimation, PopupSurface, PopupPlacement):
    """Keep the open folder alive while its contents are reordered."""

    def __init__(self, controller, key, anchor, window=None):
        self.controller, self.key, self.anchor = controller, key, anchor
        self.window = window or Gtk.Window(type=Gtk.WindowType.POPUP)
        if isinstance(self.window, Gtk.Window):
            self.window.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
            self.window.set_skip_taskbar_hint(True)
            self.window.set_skip_pager_hint(True)
        self.window.set_app_paintable(True)
        self.window.get_style_context().add_class("popup")
        self.window.set_visual(self.window.get_screen().get_rgba_visual())
        self.window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.window.connect("button-press-event", self.outside)
        self.window.connect("key-press-event", self.key_press)
        self.window.connect("focus-out-event", self.focus_lost)
        self.overlay = Gtk.Overlay()
        self.window.add(self.overlay)
        self.canvas = Gtk.DrawingArea()
        self.canvas.connect("draw", self.draw)
        self.overlay.add(self.canvas)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                               margin=26, halign=Gtk.Align.START, valign=Gtk.Align.START)
        self.overlay.add_overlay(self.content)
        header = Gtk.Box(spacing=8)
        self.title = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END, max_width_chars=24)
        self.title.get_style_context().add_class("folder-title")
        header.pack_start(self.title, True, True, 0)
        self.undo = self.header_button("edit-undo-symbolic", _("Undo"), lambda: controller.undo())
        self.gear = self.header_button("emblem-system-symbolic", _("Folder settings"), lambda: controller.preferences(key))
        header.pack_end(self.gear, False, False, 0)
        header.pack_end(self.undo, False, False, 0)
        self.content.pack_start(header, False, False, 0)
        self.grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
        self.content.pack_start(self.grid, False, False, 0)
        self.progress, self.closing, self.frame = 1., False, 0
        self.surface, self.background = None, None
        self.buttons = {}
        self.loading = True
        self.position = (0, 0)
        self.origin = (0, 0)
        self.render()

    @property
    def group(self):
        return self.controller.state.groups.get(self.key)

    def header_button(self, icon, label, callback):
        button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
        button.set_tooltip_text(label)
        button.get_style_context().add_class("flat")
        button.connect("clicked", lambda _button: callback())
        return button

    def render(self):
        if not self.group:
            self.close(False)
            return
        self.appearance = self.controller.state.core.call("surface", {"group":self.group,
            "blurStrength":self.controller.state.preferences["blurStrength"],
            "legacyGlass":self.controller.state.settings.get_boolean("glass"), "backdrop":getattr(self,"backdrop",None)})
        self.update_contrast()
        self.title.set_text(self.group["name"])
        previous, self.buttons = self.buttons, {}
        for index, entry in enumerate(self.group["apps"]):
            desktop = entry["desktop"]
            button = previous.pop(desktop,None)
            size = self.controller.state.preferences["popupIconSize"]
            if button is None:
                button = self.controller.app_button(desktop,entry["label"],size=size,key=self.key)
                self.grid.attach(button,0,0,1,1)
            self.controller.update_button(button,desktop,entry["label"],size=size,key=self.key)
            columns = min(self.controller.state.contract["layout"]["maxColumns"],len(self.group["apps"]))
            self.grid.child_set_property(button,"left-attach",index % columns)
            self.grid.child_set_property(button,"top-attach",index // columns)
            self.buttons[desktop] = button
        for button in previous.values(): button.destroy()
        self.content.show_all()
        self.gear.set_visible(self.controller.state.settings.get_boolean("customization"))
        self.undo.set_visible(self.controller.state.undo is not None)
        self.canvas.queue_draw()

    def update_contrast(self):
        self.appearance = self.controller.state.core.call("surface", {"group":self.group,
            "blurStrength":self.controller.state.preferences["blurStrength"],
            "legacyGlass":self.controller.state.settings.get_boolean("glass"), "backdrop":getattr(self,"backdrop",None)})
        style = self.window.get_style_context()
        if self.appearance["foreground"] == "#000000":
            style.add_class("folder-light")
        else:
            style.remove_class("folder-light")

    def show(self):
        self.controller.folder_tooltips(False)
        self.content.show_all()
        self.render()
        self.place()
        self.capture_background(self.rect["width"], self.rect["height"],self.show_prepared)

    def show_prepared(self):
        self.content.set_opacity(0)
        self.window.show_all()
        self.render()
        self.window.grab_add()
        self.seat = Gdk.Display.get_default().get_default_seat()
        self.grabbed = self.seat.grab(self.window.get_window(), Gdk.SeatCapabilities.POINTER,
                                     True, None, None, None, None) == Gdk.GrabStatus.SUCCESS
        def start():
            if self.controller.popup is self:
                self.loading = False
                self.animate(False)
            return GLib.SOURCE_REMOVE
        GLib.idle_add(start)

    def focus_lost(self, *_args):
        if not self.controller.dragging and not self.controller.preview:
            self.close()
        return False

    def release_pointer(self, _widget=None, event=None):
        """Release the popup grab before GTK handles an application drag."""
        if event and (event.mode != Gdk.CrossingMode.NORMAL or event.state & Gdk.ModifierType.BUTTON1_MASK):
            return False
        if getattr(self,"grabbed",False):
            self.seat.ungrab()
            self.grabbed = False
        return False

    def restore_pointer(self, _widget=None, event=None):
        if event and (event.mode != Gdk.CrossingMode.NORMAL or event.detail == Gdk.NotifyType.INFERIOR):
            return False
        if self.closing or self.controller.dragging or (event and event.state & Gdk.ModifierType.BUTTON1_MASK):
            return False
        if not getattr(self,"grabbed",False):
            self.grabbed = self.seat.grab(self.window.get_window(), Gdk.SeatCapabilities.POINTER,
                                         True, None, None, None, None) == Gdk.GrabStatus.SUCCESS
        return False

    def update_input_region(self):
        """Keep the transparent animation envelope outside the click region."""
        rect = self.rect
        region = cairo.Region(cairo.RectangleInt(rect["x"],rect["y"],rect["width"],rect["height"]))
        self.window.get_window().input_shape_combine_region(region,0,0)

    def outside(self, _window, event):
        x, y = self.position
        x, y = x+self.rect["x"], y+self.rect["y"]
        width, height = self.rect["width"], self.rect["height"]
        if not (x <= event.x_root < x + width and y <= event.y_root < y + height) and not self.controller.dragging:
            if event.button == 1:
                self.controller.folder_press({"x": event.x_root, "y": event.y_root})
            else:
                self.close()
            return True
        return False

    def key_press(self, _window, event):
        if event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            self.controller.undo()
            return True
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def close(self, animate=True):
        if self.closing:
            if not animate:
                self.destroy()
            return
        self.closing = True
        self.controller.hide_preview()
        self.window.grab_remove()
        if getattr(self,"grabbed",False):
            self.seat.ungrab()
            self.grabbed = False
        if animate and self.group and self.anchor and self.window.get_mapped():
            self.update_origin()
            self.animate(True)
        else:
            self.destroy()

    def destroy(self):
        self.release_frame_source()
        if getattr(self,"capture_job",None):
            self.capture_job.force_exit()
            self.capture_job = None
        if getattr(self,"grabbed",False):
            self.seat.ungrab()
            self.grabbed = False
        if self.frame:
            self.window.remove_tick_callback(self.frame)
            self.frame = 0
        self.window.destroy()
        if self.controller.popup is self:
            self.controller.popup = None
            self.controller.folder_tooltips(True)

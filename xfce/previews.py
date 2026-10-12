#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Show a bounded window chooser with native thumbnails when available."""

import ctypes
import os
import tempfile
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk
from i18n import _


class PreviewController:
    def cancel_hover(self):
        if self.preview_timer:
            GLib.source_remove(self.preview_timer)
            self.preview_timer = 0
        return False

    def hide_preview(self):
        self.cancel_hover()
        if self.preview:
            preview = self.preview
            self.preview = None
            preview.destroy()

    def show_preview(self, desktop, anchor):
        self.preview_timer = 0
        self.hide_preview()
        if self.closed or self.dragging or not anchor.get_mapped() or not anchor.get_window() or not self.windows.get(desktop):
            return GLib.SOURCE_REMOVE
        inline = bool(self.native and self.popup and anchor.get_toplevel() is self.popup.window)
        if inline:
            self.preview = Gtk.Popover.new(anchor)
            self.preview.set_modal(False)
            self.preview.set_transitions_enabled(False)
        elif self.native:
            from wayland_preview import create
            self.preview = create(self)
        else:
            self.preview = Gtk.Window(type=Gtk.WindowType.POPUP)
            self.preview.set_skip_taskbar_hint(True)
        layout = Gtk.Box(spacing=8, margin=12)
        self.preview.add(layout)
        capture_path = Path(__file__).resolve().parent / "capture.so"
        library = ctypes.CDLL(str(capture_path)) if not self.native and capture_path.exists() else None
        if library:
            library.dock_folders_capture.argtypes = [ctypes.c_ulong, ctypes.c_char_p]
            library.dock_folders_capture.restype = ctypes.c_int
        for window in self.windows.get(desktop, [])[:self.state.contract["layout"]["maxPreviews"]]:
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            button = Gtk.Button()
            if library:
                with tempfile.TemporaryDirectory(prefix="dock-folders-preview-") as directory:
                    image = Path(directory) / "window.png"
                    if library.dock_folders_capture(window.get_xid(), os.fsencode(image)):
                        button.add(Gtk.Image.new_from_file(str(image)))
            if not button.get_child():
                button.add(Gtk.Image.new_from_pixbuf(self.icons.get(desktop, 96, window)))
            button.connect("clicked", lambda _button, target=window: (target.activate(Gtk.get_current_event_time()), self.hide_preview()))
            column.pack_start(button, False, False, 0)
            column.pack_start(Gtk.Label(label=window.get_name(), max_width_chars=30, ellipsize=3), False, False, 0)
            close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.BUTTON)
            close.set_tooltip_text(_("Close"))
            close.connect("clicked", lambda _button, target=window: (target.close(Gtk.get_current_event_time()),self.hide_preview()))
            column.pack_start(close,False,False,0)
            layout.pack_start(column, False, False, 0)
        if inline:
            self.preview.show_all()
            self.preview.popup()
            self.preview.connect("closed", lambda _w: self.hide_preview())
            return GLib.SOURCE_REMOVE
        if self.native:
            from wayland_preview import place
            self.preview.show_all()
            place(self.preview, anchor)
            self.preview.add_events(Gdk.EventMask.LEAVE_NOTIFY_MASK)
            self.preview.connect("leave-notify-event", lambda _w, _e: self.hide_preview())
            return GLib.SOURCE_REMOVE
        self.preview.show_all()
        origin = anchor.get_window().get_origin()
        allocation = anchor.get_allocation()
        width, height = self.preview.get_size()
        monitor = Gdk.Display.get_default().get_monitor_at_window(anchor.get_window()).get_workarea()
        x = min(origin[-2] + allocation.x, monitor.x + monitor.width - width - 6)
        y = origin[-1] + allocation.y + allocation.height + 6
        if y + height > monitor.y + monitor.height:
            y = origin[-1] + allocation.y - height - 6
        self.preview.move(max(monitor.x, x), max(monitor.y, y))
        self.preview.add_events(Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.preview.connect("leave-notify-event", lambda _w, _e: self.hide_preview())
        return GLib.SOURCE_REMOVE

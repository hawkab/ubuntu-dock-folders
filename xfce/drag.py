#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Translate Xfce drag events and context actions into core commands."""



import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk
from state import EXTENSION
from windows import desktop_info
import sys
sys.path.insert(0, str(EXTENSION / "app"))
from i18n import _

TARGET = "application/x-ubuntu-dock-folders-app"
DEST_DEFAULTS = Gtk.DestDefaults.MOTION | Gtk.DestDefaults.HIGHLIGHT
TARGETS = [Gtk.TargetEntry.new(TARGET, 0, 0),
           Gtk.TargetEntry.new("text/uri-list", Gtk.TargetFlags.OTHER_APP, 1)]



class DragController:
    def request_drop(self, button, context, _x, _y, timestamp):
        """Request a matching payload; finish the drop after its transaction."""
        target = button.drag_dest_find_target(context, None)
        if target is None:
            return False
        button.drag_get_data(context, target, timestamp)
        return True

    def drag_data(self, _button, _context, selection, _info, _time, desktop):
        """Encode the desktop ID for the internal application drag target."""
        selection.set(selection.get_target(), 8, desktop.encode("utf-8"))

    def drag_failed(self, _button, _context, result, desktop, key):
        """Extract a folder app dropped outside a target; retain cancelled drags."""
        if getattr(self, "drop_committed", False):
            return True
        if key and result == Gtk.DragResult.NO_TARGET and self.state.extract(desktop):
            self.pending = True
            return True
        return False

    def context_menu(self, button, event, desktop, group):
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        actions = [(_("Folder settings"), lambda: self.preferences(next(key for key, value in self.state.groups.items() if value is group)))] if group else []
        if group or desktop_info(desktop):
            item = Gtk.CheckMenuItem(label=_("Pin to dock"))
            item.set_active(desktop in self.state.favorites)
            item.connect("activate", lambda _item: self.pin(desktop))
            menu.append(item)
        actions.append((_("General folder settings"), self.preferences))
        for label, callback in actions:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _item, action=callback: action())
            menu.append(item)
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, event)
        return True

    def pin(self, desktop):
        self.state.execute({"operation":"pin","desktop":desktop})
        self.queue_render()

    def drag_begin(self, _button, context, desktop):
        self.dragging = True
        self.drag_context = context
        self.drop_committed = False
        self.hide_preview()
        Gtk.drag_set_icon_pixbuf(context, self.icons.get(desktop, 48), 24, 24)

    def drag_end(self, *_args):
        if getattr(self, "drop_timer", 0):
            GLib.source_remove(self.drop_timer)
            self.drop_timer = 0
        self.drag_context = None
        self.drop_committed = False
        self.dragging = False
        if self.popup:
            self.popup.restore_pointer()
        if self.pending:
            self.pending = False
            self.queue_render()

    def finish_embedded_drop(self, context):
        """Release a local drag when XEmbed omits source completion."""
        self.drop_timer = 0
        if not self.closed and self.dragging and getattr(self, "drag_context", None) is context:
            Gtk.drag_cancel(context)
        return GLib.SOURCE_REMOVE

    def drop(self, _button, context, _x, _y, selection, info, timestamp, target, key, group):
        desktop = None
        if info == 0:
            try:
                desktop = bytes(selection.get_data() or b"").decode("utf-8")
            except UnicodeDecodeError:
                pass
        if info == 1:
            uris = selection.get_uris() or []
            filename = Gio.File.new_for_uri(uris[0]).get_path() if len(uris) == 1 else None
            desktop = next((app.get_id() for app in self.tracker.catalog.values()
                            if hasattr(app, "get_filename") and app.get_filename() == filename), None)
        changed = False
        if desktop and desktop_info(desktop):
            if key:
                changed = self.state.move(desktop, key, target)
            elif group:
                group_key = next((key for key, value in self.state.groups.items() if value["id"] == group["id"]), None)
                if group_key is not None:
                    changed = self.state.move(desktop, group_key)
            elif target:
                changed = self.state.create(desktop, target, _("New Folder"))
            else:
                changed = self.state.extract(desktop)
        Gtk.drag_finish(context, changed, False, timestamp)
        if self.dragging and getattr(self, "drag_context", None):
            self.drop_committed = changed
            if getattr(self, "drop_timer", 0):
                GLib.source_remove(self.drop_timer)
            self.drop_timer = GLib.timeout_add(150, self.finish_embedded_drop, self.drag_context)
        if changed:
            self.pending = True
            self.queue_render()

    def undo(self):
        if self.state.undo_last():
            self.queue_render()

    def hover(self, desktop, anchor):
        self.cancel_hover()
        if self.windows.get(desktop) and not self.dragging:
            self.preview_timer = GLib.timeout_add(self.state.contract["layout"]["previewDelay"], self.show_preview, desktop, anchor)
        return False

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Create launcher buttons and refresh their current folder bindings."""

import json
from gi.repository import Gdk, Gtk, Pango
from icons import DockIcon
from drag import TARGETS, DEST_DEFAULTS


class LauncherButtons:
    def update_button(self, button, desktop, label, size=None, key=None, group=None):
        """Refresh a retained button without changing its identity or drag handlers."""
        icon = button._dock_icon
        button._dock_group = group
        icon.group = group
        icon.window = next(iter(self.windows.get(desktop,[])),None)
        column = button.get_child()
        text = button._dock_label
        if key or (group and group.get("showLabel")):
            if text is None:
                text = Gtk.Label(max_width_chars=12,ellipsize=3,wrap=bool(key))
                text.get_style_context().add_class("folder-app" if key else "folder-label")
                column.pack_start(text,False,False,0)
                button._dock_label = text
            text.set_text(label)
            if key:
                text.set_max_width_chars(max(7,round((size or 56)/7)))
                text.set_lines(2)
            else:
                text.override_font(Pango.FontDescription(f"Sans {self.state.settings.get_double('font-size')}px"))
        elif text:
            text.destroy()
            text = button._dock_label = None
        cross = self.size-4 if self.embedded and group and not key else None
        if cross and text and self.orientation == Gtk.Orientation.HORIZONTAL:
            cross = max(8,cross-text.get_layout().get_pixel_size()[1]-column.get_spacing())
        signature = json.dumps([group,size,self.size,cross,self.orientation,self.state.preferences],sort_keys=True)
        if signature != getattr(button,"_layout_signature",None):
            button._layout_signature = signature
            icon.size,icon.cross_size = size or max(24,self.size-4),cross
            icon.appearance = self.state.core.call("appearance",group) if group else None
            icon.update_layout()
            icon.sync_orbit()
        button.set_tooltip_text(label if key or not group or not group.get("showLabel") else None)
        if group and self.popup: button.set_has_tooltip(False)
        icon.queue_draw()

    def app_button(self, desktop, label, size=None, key=None, group=None):
        button = Gtk.Button()
        button._grouping_enabled = self.state.settings.get_boolean('enabled')
        button._dock_group = group
        button._dock_icon = None
        button._dock_label = None
        button.get_style_context().add_class("dock-folder-button")
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        windows = self.windows.get(desktop, [])
        text = None
        if key or (group and group.get("showLabel")):
            text = Gtk.Label(label=label, max_width_chars=12, ellipsize=3, wrap=bool(key))
            text.get_style_context().add_class("folder-app" if key else "folder-label")
            if key:
                text.set_max_width_chars(max(7, round((size or 56)/7)))
                text.set_lines(2)
            if not key:
                text.override_font(Pango.FontDescription(
                    f"Sans {self.state.settings.get_double('font-size')}px"))
        cross_size = self.size - 4 if self.embedded and group and not key else None
        if cross_size and text and self.orientation == Gtk.Orientation.HORIZONTAL:
            cross_size = max(8, cross_size - text.get_layout().get_pixel_size()[1] - column.get_spacing())
        icon = DockIcon(self, desktop, group, size or max(24, self.size - 4),
                        windows[0] if windows else None, cross_size)
        column.pack_start(icon, False, False, 0)
        if text:
            column.pack_start(text, False, False, 0)
        button.add(column)
        button._dock_icon,button._dock_label = icon,text
        if key or not group or not group.get("showLabel"):
            button.set_tooltip_text(label)
        if group and self.popup:
            button.set_has_tooltip(False)
        button.connect("clicked", lambda _button: self.toggle(_button._dock_group, _button) if _button._dock_group else self.activate(desktop))
        button.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        button.connect("enter-notify-event", lambda _b, _e: self.hover(desktop, button) if not group else icon.hover(True))
        button.connect("leave-notify-event", lambda _b, _e: self.cancel_hover() if not group else icon.hover(False))
        button.connect("button-press-event", lambda _button,event: self.application_press(_button,event,desktop,_button._dock_group))
        if key:
            button.connect("enter-notify-event",lambda widget,event:
                self.popup.release_pointer(widget,event) if self.popup and self.popup.key == key else False)
            button.connect("leave-notify-event",lambda widget,event:
                self.popup.restore_pointer(widget,event) if self.popup and self.popup.key == key else False)
        button.add_events(Gdk.EventMask.SCROLL_MASK)
        button.connect("scroll-event", lambda _button,event: self.application_scroll(_button,event,desktop,_button._dock_group))
        if self.state.settings.get_boolean("enabled"):
            if not group and not desktop.startswith("wm:"):
                button.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, TARGETS[:1], Gdk.DragAction.MOVE)
                button.connect("drag-data-get", self.drag_data, desktop)
                button.connect("drag-begin", self.drag_begin, desktop)
                button.connect("drag-end", self.drag_end)
                button.connect("drag-failed", self.drag_failed, desktop, key)
            button.drag_dest_set(DEST_DEFAULTS, TARGETS, Gdk.DragAction.MOVE)
            button.connect("drag-drop", self.request_drop)
            button.connect("drag-data-received", lambda *args: self.drop(*args,desktop,key,button._dock_group))
        return button

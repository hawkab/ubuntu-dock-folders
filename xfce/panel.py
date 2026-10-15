#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Own the Xfce panel lifecycle and adapt launch and drag events."""

import argparse
import os
import subprocess
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gdk, GdkX11, GLib, Gtk, Pango
from state import EXTENSION, FolderState
from windows import WindowTracker, desktop_info
sys.path.insert(0, str(EXTENSION / "app"))
from i18n import set_ui_direction

from icons import IconCache
from buttons import LauncherButtons
from folders import FolderController
from drag import DragController, TARGETS, DEST_DEFAULTS
from previews import PreviewController
from application_actions import ApplicationActions

class Controller(LauncherButtons, DragController, PreviewController, FolderController, ApplicationActions):
    """Reconcile application changes once and update running indicators in place."""

    def __init__(self, socket=0, size=48, orientation=0, host=None):
        wayland = not isinstance(Gdk.Display.get_default(), GdkX11.X11Display)
        if socket and wayland:
            raise RuntimeError("XEmbed sockets require an X11 display.")
        self.standalone = not socket and host is None
        if self.standalone and wayland:
            from preview_host import create
            host = create(size, orientation)
        set_ui_direction()
        self.state = FolderState()
        self.icons = IconCache()
        self.size, self.orientation = size, Gtk.Orientation(orientation)
        self.native = host is not None
        self.embedded = bool(socket) or self.native
        self.popup, self.preview, self.preview_timer, self.update_timer = None, None, 0, 0
        self.dragging, self.pending, self.buttons = False, False, {}
        self.windows = {}
        self.render_count = 0
        self.closed = False
        self.command_buffer = b""
        self.tracker = WindowTracker(self.windows_changed, self.state.core)
        self.tracker.set_groups(self.state.groups)
        self.tracker.signals.append((self.tracker.screen,
            self.tracker.screen.connect("active-window-changed", self.focus_changed)))
        self.window = host.get_toplevel() if host else Gtk.Plug.new(socket) if socket else Gtk.Window()
        self.box = Gtk.Box(orientation=self.orientation, spacing=2)
        self.box.connect("destroy", self.shutdown)
        if not self.native or self.standalone:
            self.window.set_title("Dock folders")
            self.window.add(self.box)
        if self.standalone:
            self.window.connect("destroy", lambda *_args: Gtk.main_quit() if Gtk.main_level() else None)
        self.settings_signal = self.state.settings.connect("changed", self.settings_changed)
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            .dock-folder-button { background: transparent; border: none; padding: 2px; box-shadow: none; }
            .dock-folder-button:hover { background: rgba(255,255,255,.10); border-radius: 12px; }
            .folder-title { font-size: 18px; font-weight: bold; color: white; }
            .folder-app { color: white; }
            .folder-light .folder-title, .folder-light .folder-app, .folder-light button { color: black; }
            window.popup { background: transparent; }
        """)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.render()
        if not self.native or self.standalone:
            self.window.show_all()
        if socket:
            GLib.io_add_watch(sys.stdin, GLib.IOCondition.IN | GLib.IOCondition.HUP, self.command)

    def preferences(self, key=None):
        self.hide_preview()
        if self.popup:
            self.popup.close(False)
        env = os.environ.copy()
        env["DOCK_FOLDERS_DESKTOP"] = "xfce"
        subprocess.Popen(["/usr/bin/python3", str(EXTENSION / "app/preferences.py"), key or "--global"], env=env)

    def focus_changed(self, screen, _previous):
        active = screen.get_active_window()
        if self.popup and active and not active.is_skip_tasklist() and not self.dragging:
            self.popup.close()

    def settings_changed(self, _settings, _key):
        self.queue_render()

    def queue_render(self):
        if self.dragging:
            self.pending = True
        elif not self.update_timer and not self.closed:
            self.update_timer = GLib.idle_add(self.update)

    def update(self):
        self.update_timer = 0
        if self.state.load():
            self.state.clean()
        self.tracker.set_groups(self.state.groups)
        self.render()
        return GLib.SOURCE_REMOVE

    def windows_changed(self, installed):
        if self.closed:
            return
        if installed:
            self.icons.clear()
            if self.state.clean():
                self.queue_render()
        previous = set(self.windows)
        self.windows = self.tracker.by_app()
        grouped = self.state.grouped if self.state.settings.get_boolean("enabled") else set()
        if (set(self.windows) - grouped - set(self.state.favorites)) != (previous - grouped - set(self.state.favorites)):
            self.queue_render()
        for button in self.buttons.values():
            button.queue_draw()
        if self.popup:
            self.popup.grid.queue_draw()

    def render(self):
        self.hide_preview()
        previous, self.buttons = self.buttons, {}
        self.render_count += 1
        groups = {group["id"] + ".desktop": group for group in self.state.groups.values()}
        if hasattr(self,"orbit_phases"):
            self.orbit_phases = {key:value for key,value in self.orbit_phases.items()
                                 if key + ".desktop" in groups}
        enabled = self.state.settings.get_boolean("enabled")
        favorites = self.state.favorites if enabled else self.state.core.call("favorites", {
            "groups":self.state.groups,"favorites":self.state.favorites})
        grouped = self.state.grouped if enabled else set()
        desktops = list(dict.fromkeys(favorites + [desktop for desktop in self.windows if desktop not in grouped]))
        for desktop in desktops:
            group = groups.get(desktop) if enabled else None
            info = desktop_info(desktop)
            windows = self.windows.get(desktop, [])
            if not group and not info and not windows:
                continue
            label = group["name"] if group else info.get_name() if info else windows[0].get_name()
            button = previous.pop(desktop,None)
            if button and (bool(button._dock_group) != bool(group) or button._grouping_enabled != enabled):
                button.destroy()
                button = None
            if button is None:
                button = self.app_button(desktop, label, group=group)
                self.box.pack_start(button,False,False,0)
            self.update_button(button,desktop,label,group=group)
            self.buttons[desktop] = button
            self.box.reorder_child(button,len(self.buttons)-1)
        for button in previous.values():
            button.destroy()
        self.box.drag_dest_set(DEST_DEFAULTS, TARGETS, Gdk.DragAction.MOVE)
        if not getattr(self, "box_drop", False):
            self.box.connect("drag-drop", self.request_drop)
            self.box.connect("drag-data-received", self.drop, None, None, None)
            self.box_drop = True
        self.box.show_all()
        if self.popup:
            if not enabled or self.popup.key not in self.state.groups:
                self.popup.close(False)
            else:
                self.popup.anchor = self.buttons.get(self.popup.group["id"] + ".desktop")
                self.popup.render()
                if not self.dragging and not self.popup.frame:
                    self.popup.place()

    def layout(self, size, orientation):
        """Apply panel size and orientation without restarting the controller."""
        if (self.size, self.orientation) == (size, orientation):
            return
        self.size, self.orientation = size, Gtk.Orientation(orientation)
        self.box.set_orientation(self.orientation)
        self.queue_render()

    def command(self, stream, condition):
        if condition & GLib.IOCondition.HUP:
            self.shutdown()
            return GLib.SOURCE_REMOVE
        chunk = os.read(stream.fileno(), 4096)
        if not chunk:
            self.shutdown()
            return GLib.SOURCE_REMOVE
        self.command_buffer += chunk
        messages = self.command_buffer.split(b"\n")
        self.command_buffer = messages.pop()
        for line in messages:
            message = line.decode("utf-8").strip().split()
            if message[:1] == ["preferences"]:
                self.preferences()
            elif message[:1] == ["layout"] and len(message) == 3:
                self.layout(int(message[1]), int(message[2]))
        return GLib.SOURCE_CONTINUE

    def shutdown(self, *_args):
        if self.closed:
            return
        self.closed = True
        if getattr(self, "drop_timer", 0):
            GLib.source_remove(self.drop_timer)
            self.drop_timer = 0
        if getattr(self, "drag_context", None):
            Gtk.drag_cancel(self.drag_context)
        if self.popup:
            self.popup.close(False)
        self.hide_preview()
        if self.update_timer:
            GLib.source_remove(self.update_timer)
            self.update_timer = 0
        self.state.settings.disconnect(self.settings_signal)
        self.tracker.close()
        self.icons.close()
        self.state.close()
        if (not self.native or self.standalone) and Gtk.main_level():
            Gtk.main_quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", type=int, default=0)
    parser.add_argument("--size", type=int, default=48)
    parser.add_argument("--orientation", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    try:
        Controller(args.socket, args.size, args.orientation)
    except RuntimeError as error:
        parser.exit(1, str(error) + "\n")
    Gtk.main()


if __name__ == "__main__":
    main()

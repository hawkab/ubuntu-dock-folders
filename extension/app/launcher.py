#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Fallback launcher when the Shell extension is unavailable."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk
from i18n import _, set_ui_direction
from settings import groups


class GroupLauncher(Adw.Application):
    def __init__(self, group):
        super().__init__(application_id=group["id"])
        self.group = group
        self.window = None
        self.connect("activate", self.activate_window)

    def activate_window(self, _app):
        if self.window is None:
            self.window = Adw.ApplicationWindow(
                application=self,
                title=self.group["name"],
                default_width=min(760, max(320, 150 * len(self.group["apps"]))),
                default_height=260,
            )
            toolbar = Adw.ToolbarView()
            toolbar.add_top_bar(Adw.HeaderBar())
            self.window.set_content(toolbar)
            content = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=20,
                margin_top=20,
                margin_bottom=24,
                margin_start=24,
                margin_end=24,
            )
            toolbar.set_content(content)
            prompt = Gtk.Label(label=_("Choose an application"))
            prompt.add_css_class("dim-label")
            content.append(prompt)
            tiles = Gtk.FlowBox(
                selection_mode=Gtk.SelectionMode.NONE,
                homogeneous=True,
                max_children_per_line=4,
                row_spacing=12,
                column_spacing=12,
            )
            content.append(tiles)
            for entry in self.group["apps"]:
                info = Gio.DesktopAppInfo.new(entry["desktop"])
                icon = info.get_icon() if info else Gio.ThemedIcon.new("application-x-executable")
                label = entry["label"].replace("\n", " ")
                tile = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL,
                    spacing=12,
                    margin_start=12,
                    margin_end=12,
                    margin_top=12,
                    margin_bottom=12,
                )
                tile.append(Gtk.Image(gicon=icon, pixel_size=56))
                tile.append(Gtk.Label(label=label, wrap=True, max_width_chars=18))
                button = Gtk.Button(child=tile, tooltip_text=_("Open %s") % label)
                button.add_css_class("flat")
                button.connect("clicked", self.launch, entry["desktop"])
                tiles.insert(button, -1)
        self.window.present()

    def launch(self, _button, desktop):
        try:
            info = Gio.DesktopAppInfo.new(desktop)
            if info is None:
                raise RuntimeError(_("Application launcher not found."))
            context = self.window.get_display().get_app_launch_context()
            if not info.launch([], context):
                raise RuntimeError(_("Could not launch the application."))
        except (GLib.Error, RuntimeError) as error:
            dialog = Adw.MessageDialog(
                transient_for=self.window,
                modal=True,
                heading=_("Could not open the application"),
                body=str(error),
            )
            dialog.add_response("close", _("Close"))
            dialog.present()
            return
        self.window.close()


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else ""
    group = groups().get(key)
    if group is None:
        raise SystemExit(_("Folder not found."))
    set_ui_direction()
    GroupLauncher(group).run([sys.argv[0]])

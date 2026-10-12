#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Apply shared folder activation decisions to anchored GTK windows."""

from folder_popup import FolderPopup


class FolderController:
    def folder_tooltips(self, enabled):
        """Keep folder hints inactive while a popup owns pointer interaction."""
        for group in self.state.groups.values():
            button = self.buttons.get(group["id"] + ".desktop")
            if button:
                button.set_has_tooltip(enabled and not group.get("showLabel", False))

    def folder_anchors(self):
        """Return mapped folder bounds in the display's event coordinate space."""
        origin = self.window.get_window().get_origin()[-2:]
        anchors = []
        for key, group in self.state.groups.items():
            button = self.buttons.get(group["id"] + ".desktop")
            if button and button.get_mapped():
                x, y = button.translate_coordinates(self.window, 0, 0)
                anchors.append({"key": key, "x": origin[0] + x, "y": origin[1] + y,
                                "width": button.get_allocated_width(), "height": button.get_allocated_height()})
        return anchors

    def folder_press(self, point):
        """Resolve a captured dock press without replaying it to GTK."""
        self.apply_folder_interaction(self.state.core.call("folderInteraction", {
            "current": self.popup.key if self.popup else None,
            "point": point, "anchors": self.folder_anchors(),
        }))

    def toggle(self, group, _anchor):
        key = next((key for key, value in self.state.groups.items() if value["id"] == group["id"]), None)
        if key is None:
            return
        self.apply_folder_interaction(self.state.core.call("folderInteraction", {
            "current": self.popup.key if self.popup else None, "target": key,
        }))

    def apply_folder_interaction(self, decision):
        if decision["close"] and self.popup:
            self.popup.close(not decision["open"])
        key = decision["open"]
        group = self.state.groups.get(key)
        anchor = self.buttons.get(group["id"] + ".desktop") if group else None
        if anchor:
            popup_type = FolderPopup
            if self.native:
                from wayland_popup import WaylandPopup
                popup_type = WaylandPopup
            self.popup = popup_type(self, key, anchor)
            self.popup.show()

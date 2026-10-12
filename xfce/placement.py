# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Place the card beside its current anchor and include the animation's origin."""

from gi.repository import Gdk, Gtk


class PopupPlacement:
    def anchor_rect(self):
        root = self.controller.window.get_window().get_origin()
        x, y = self.anchor.translate_coordinates(self.controller.window, 0, 0)
        allocation = self.anchor.get_allocation()
        return root[-2]+x, root[-1]+y, allocation.width, allocation.height

    def update_origin(self):
        ax, ay, aw, ah = self.anchor_rect()
        self.origin = ax+aw/2-self.position[0], ay+ah/2-self.position[1]

    def place(self):
        self.content.set_margin_start(26)
        self.content.set_margin_top(26)
        _minimum, natural = self.content.get_preferred_size()
        width, height = max(160, natural.width), max(160, natural.height)
        ax, ay, aw, ah = self.anchor_rect()
        area = Gdk.Display.get_default().get_monitor_at_point(ax, ay).get_workarea()
        width, height = min(width, area.width-12), min(height, area.height-12)
        if self.controller.orientation == Gtk.Orientation.HORIZONTAL:
            x, y = ax+aw/2-width/2, ay+ah+10
            self.edge = 1
            if y+height > area.y+area.height:
                y, self.edge = ay-height-10, 0
        else:
            x, y = ax+aw+10, ay+ah/2-height/2
            self.edge = 2
            if x+width > area.x+area.width:
                x, self.edge = ax-width-10, 3
        x = int(max(area.x+6, min(x, area.x+area.width-width-6)))
        y = int(max(area.y+6, min(y, area.y+area.height-height-6)))
        left, top = int(min(x, ax+aw/2)), int(min(y, ay+ah/2))
        right, bottom = int(max(x+width, ax+aw/2+1)), int(max(y+height, ay+ah/2+1))
        self.position = left, top
        self.rect = {"x": x-left, "y": y-top, "width": width, "height": height}
        self.origin = ax+aw/2-left, ay+ah/2-top
        self.content.set_margin_start(self.rect["x"]+26)
        self.content.set_margin_top(self.rect["y"]+26)
        self.content.set_margin_end(26)
        self.content.set_margin_bottom(26)
        self.canvas.set_size_request(right-left, bottom-top)
        self.position_window(left, top, right-left, bottom-top)
        if self.window.get_mapped() and not self.frame:
            self.update_input_region()

    def position_window(self, left, top, width, height):
        self.window.resize(width, height)
        self.window.move(left, top)

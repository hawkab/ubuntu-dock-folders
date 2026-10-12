# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Advance active miniatures together on the panel's GTK frame clock."""

from gi.repository import GLib


class IconMotion:
    """Batch core calculations and stop the frame callback when all icons rest."""

    def __init__(self, controller):
        self.controller = controller
        self.icons = set()
        self.callback = 0

    def add(self, icon):
        self.icons.add(icon)
        if not self.callback:
            self.callback = self.controller.box.add_tick_callback(self.tick)

    def remove(self, icon):
        if icon.orbit_timer or icon.hover_timer:
            return
        self.icons.discard(icon)
        if not self.icons and self.callback:
            self.controller.box.remove_tick_callback(self.callback)
            self.callback = 0

    def tick(self, _widget, clock):
        now = clock.get_frame_time()
        pending = []
        for icon in list(self.icons):
            if not icon.orbit_allowed():
                icon.orbit_timer = icon.hover_timer = 0
                self.icons.discard(icon)
                continue
            interval = 16 if icon.hover_timer else self.controller.state.contract["layout"]["orbitFrameInterval"]
            if now-icon.orbit_last < interval*1000:
                continue
            if icon.hover_timer:
                fraction = min(1.,(now-icon.hover_start)/icon.hover_duration)
                icon.progress = icon.hover_initial+(icon.hover_target-icon.hover_initial)*fraction*fraction*(3-2*fraction)
                if fraction == 1:
                    icon.hover_timer = 0
            request = icon.layout_request((now-icon.orbit_last)/1000)
            request.pop("values")
            pending.append((icon,request))
        if pending:
            states = self.controller.state.core.call("orbitMiniaturesBatch",{
                "values":self.controller.state.preferences,"items":[request for _icon,request in pending]})
            for (icon,_request),state in zip(pending,states):
                icon.apply_layout(state)
                icon.orbit_last = now
                icon.orbit_timer = int(state["active"])
                icon.queue_draw()
                if not icon.orbit_timer and not icon.hover_timer:
                    self.icons.discard(icon)
        if self.icons:
            return GLib.SOURCE_CONTINUE
        self.callback = 0
        return GLib.SOURCE_REMOVE

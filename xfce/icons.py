#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Paint application icons and animate shared miniature formations."""

import math
from collections import OrderedDict

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from windows import desktop_info

from drawing import color
from icon_motion import IconMotion

class IconCache:
    """Cache transparent application icons at their final display size."""

    def __init__(self):
        self.icons = OrderedDict()
        self.sources = OrderedDict()
        self.bytes = 0
        self.budget = 16 * 1024 * 1024
        self.limit = 256
        self.theme = Gtk.IconTheme.get_default()
        self.signal = self.theme.connect("changed",lambda *_args: self.clear())

    def clear(self):
        self.icons.clear()
        self.sources.clear()
        self.bytes = 0

    def close(self):
        self.theme.disconnect(self.signal)
        self.clear()

    def get(self, desktop, size, window=None, scale=1):
        if desktop not in self.sources:
            info = desktop_info(desktop)
            self.sources[desktop] = info.get_icon() if info else None
            if len(self.sources) > self.limit: self.sources.popitem(last=False)
        icon = self.sources[desktop]
        self.sources.move_to_end(desktop)
        fallback = window.get_icon() if icon is None and window else None
        key = icon.to_string() if icon else (desktop,hash(fallback) if fallback else None), size, scale
        if key not in self.icons:
            themed = self.theme.lookup_by_gicon_for_scale(icon, size, scale, Gtk.IconLookupFlags.FORCE_SIZE) if icon else None
            try:
                pixbuf = themed.load_icon() if themed else None
            except GLib.Error:
                pixbuf = None
            if pixbuf is None and fallback:
                pixbuf = fallback
                if pixbuf:
                    pixbuf = pixbuf.scale_simple(size*scale, size*scale, GdkPixbuf.InterpType.BILINEAR)
            if pixbuf is None:
                pixbuf = self.theme.load_icon("application-x-executable", size, Gtk.IconLookupFlags.FORCE_SIZE)
            self.icons[key] = pixbuf
            self.bytes += pixbuf.get_rowstride()*pixbuf.get_height()
            while len(self.icons) > 1 and (len(self.icons) > self.limit or self.bytes > self.budget):
                _key,old = self.icons.popitem(last=False)
                self.bytes -= old.get_rowstride()*old.get_height()
        else:
            self.icons.move_to_end(key)
        return self.icons[key]


class DockIcon(Gtk.DrawingArea):
    """Paint cached application icons using the portable miniature geometry."""

    def __init__(self, controller, desktop, group=None, size=42, window=None, cross_size=None):
        super().__init__()
        self.controller, self.desktop, self.group = controller, desktop, group
        if not hasattr(controller,"icon_motion"): controller.icon_motion = IconMotion(controller)
        self.size, self.window = size, window
        self.cross_size = cross_size
        self.progress, self.hover_timer, self.hover_target = 0., 0, 0.
        self.orbit_angle, self.orbit_timer, self.orbit_last, self.hovered = 0., 0, 0, False
        self.orbit_velocity = 0.
        self.orbit_progress = 0.
        if group:
            if not hasattr(controller,"orbit_phases"): controller.orbit_phases = {}
            self.orbit_angle = controller.orbit_phases.get(group["id"],0.)
        self.appearance = controller.state.core.call("appearance",group) if group else None
        self.layout = None
        self.update_layout()
        self.connect("draw", self.draw_icon)
        self.connect("destroy", self.stop_hover)
        self.connect("destroy", self.stop_orbit)
        self.connect("map", self.sync_orbit)
        self.connect("unmap", self.stop_hover)
        self.connect("unmap", self.stop_orbit)

    def update_layout(self, elapsed=0):
        if not self.group:
            self.set_size_request(self.size, self.size)
            return
        return self.apply_layout(self.controller.state.core.call("orbitMiniatures",self.layout_request(elapsed)))

    def layout_request(self, elapsed=0):
        settings = self.controller.state.preferences
        body = self.size * settings["groupIconSize"] / 100
        if self.cross_size is not None:
            minimum, maximum, _step = next(item["range"] for item in self.controller.state.contract["preferences"]
                                         if item["name"] == "groupIconSize")
            fraction = (settings["groupIconSize"]-minimum)/(maximum-minimum)
            body = self.cross_size * (.45+.55*fraction)
        mode = next(item for item in self.controller.state.contract["hoverEffects"] if item["key"] == settings["hoverEffect"])
        rotation = self.group.get("iconRotation", 0)
        return {"angle": self.orbit_angle, "velocity": self.orbit_velocity,
            "previousProgress": self.orbit_progress, "hoverProgress": self.progress,
            "elapsed": elapsed, "values": settings, "hovered": self.hovered, "allowed": self.orbit_allowed(),
            "args": [body, len(self.group["apps"]),
            settings["groupMiniIconSize"] / 100, self.cross_size or self.controller.size - 4,
            self.controller.orientation == Gtk.Orientation.VERTICAL, self.group["id"], rotation,
            self.group.get("alwaysStack", False), self.progress if mode["cards"] else 0, mode["cards"]]}

    def apply_layout(self, state):
        self.orbit_angle, self.layout = state["angle"], state["layout"]
        self.orbit_velocity = state["velocity"]
        self.orbit_progress = self.progress
        self.controller.orbit_phases[self.group["id"]] = self.orbit_angle
        self.body = self.layout["bodySize"]
        self.set_size_request(math.ceil(self.layout["width"]), math.ceil(self.layout["height"]))
        return state["active"]

    def orbit_allowed(self):
        return self.get_mapped() and not self.controller.dragging and not getattr(self.controller,"closed",False) \
            and Gtk.Settings.get_default().get_property("gtk-enable-animations")

    def sync_orbit(self, *_args):
        if not self.group or getattr(self.controller,"closed",False):
            return
        state = self.controller.state.core.call("orbitFrame", {"velocity": self.orbit_velocity,
            "values": self.controller.state.preferences, "hovered": self.hovered, "allowed": self.orbit_allowed()})
        self.orbit_velocity = state["velocity"]
        if not state["active"]:
            self.stop_orbit()
        elif not self.orbit_timer:
            self.orbit_last = GLib.get_monotonic_time()
            self.orbit_timer = 1
            self.controller.icon_motion.add(self)

    def stop_orbit(self, *_args):
        self.orbit_timer = 0
        self.controller.icon_motion.remove(self)
        self.orbit_velocity = 0.

    def paint(self, context, desktop, size, x, y):
        pixbuf = self.controller.icons.get(desktop, max(1, round(size)), self.window,self.get_scale_factor())
        context.save()
        context.translate(x,y)
        context.scale(size/pixbuf.get_width(),size/pixbuf.get_height())
        Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
        context.paint();context.restore()

    def draw_icon(self, _widget, context):
        width, height = self.get_allocated_width(), self.get_allocated_height()
        if self.group:
            group, layout = self.group, self.layout
            ox, oy = (width-self.body)/2, (height-self.body)/2
            context.set_source_rgba(*color(self.appearance["dockColor"], self.appearance["dockOpacity"]))
            context.arc(width/2, height/2, self.body*self.controller.state.contract["layout"]["circleScale"]/2, 0, math.tau)
            context.fill()
            mini = layout["size"]
            for entry, item in zip(group["apps"], layout["items"]):
                context.save()
                translucent = item["opacity"] < 1
                if translucent: context.push_group()
                context.translate(ox+item["x"]+mini/2, oy+item["y"]+mini/2)
                context.rotate(math.radians(item["rotation"]))
                if layout["cardOpacity"]:
                    context.rectangle(-mini/2,-mini/2,mini,mini)
                    context.set_source_rgba(*color(self.appearance["dockColor"],layout["cardOpacity"]))
                    context.fill_preserve(); context.set_source_rgba(1,1,1,.25*layout["cardOpacity"])
                    context.set_line_width(1); context.stroke()
                context.rotate(math.radians(item["glyphRotation"]))
                self.paint(context,entry["desktop"],mini,-mini/2,-mini/2)
                if translucent:
                    context.pop_group_to_source()
                    context.paint_with_alpha(item["opacity"])
                context.restore()
            running = any(self.controller.windows.get(entry["desktop"]) for entry in group["apps"])
        else:
            size = min(width,height,self.size)
            self.paint(context,self.desktop,max(12,size-8),(width-size)/2+4,(height-size)/2+2)
            running = bool(self.controller.windows.get(self.desktop))
        if running:
            context.set_source_rgba(.65,.86,.28,1)
            context.arc(width/2,height-3,2.3,0,math.tau); context.fill()
        return False

    def hover(self, active):
        self.hovered = bool(active)
        self.sync_orbit()
        mode = next(item for item in self.controller.state.contract["hoverEffects"] if item["key"] == self.controller.state.preferences["hoverEffect"])
        if not mode["rotate"] and not (mode["cards"] and self.layout and self.layout["stacked"]):
            return False
        self.stop_hover()
        self.hover_target = 1. if active and not self.controller.dragging else 0.
        self.hover_start, self.hover_initial = GLib.get_monotonic_time(), self.progress
        duration = self.controller.state.core.call("hoverDuration", self.controller.state.preferences["hoverSpeed"]) * 1000
        if not duration:
            self.progress = self.hover_target
            self.update_layout(); self.queue_draw()
            return False
        self.hover_duration = duration
        self.hover_timer = 1
        self.orbit_last = self.hover_start
        self.controller.icon_motion.add(self)
        return False

    def stop_hover(self, *_args):
        self.hover_timer = 0
        self.controller.icon_motion.remove(self)

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Render the shared deformation kernel on a bounded Cairo mesh."""

import cairo
import uuid
from gi.repository import GLib


class PopupAnimation:
    """Animate a cached card; no captures or widget creation occur during frames."""

    def snapshot(self):
        self.release_frame_source()
        self.window.check_resize()
        rect = self.rect
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, rect["width"], rect["height"])
        context = cairo.Context(self.surface)
        self.paint_background(context, rect["width"], rect["height"])
        self.content.set_opacity(1)
        context.translate(26, 26)
        self.content.draw(context)
        self.content.set_opacity(0)
        self.sources = [{"x": rect["x"] + rect["width"] * x / 8,
                         "y": rect["y"] + rect["height"] * y / 8}
                        for y in range(9) for x in range(9)]

    def animate(self, closing):
        if self.frame:
            self.window.remove_tick_callback(self.frame)
        self.closing = closing
        self.snapshot()
        preferences = self.controller.state.preferences
        self.mode, self.speed = preferences["animation"], preferences["animationSpeed"]
        response = self.animation_frame(0, not closing)
        duration = response["duration"] * 1000
        if not duration:
            self.finish_animation(closing)
            return
        start = GLib.get_monotonic_time()

        def tick(_widget, clock):
            fraction = min(1., max(0., (clock.get_frame_time() - start) / duration))
            self.animation_frame(fraction, not closing)
            self.canvas.queue_draw()
            if fraction < 1:
                return GLib.SOURCE_CONTINUE
            self.finish_animation(closing)
            return GLib.SOURCE_REMOVE

        self.frame = self.window.add_tick_callback(tick)

    def animation_frame(self, time, opening):
        if not getattr(self,"frame_source",None):
            self.frame_source = uuid.uuid4().hex
            self.controller.state.core.call("registerFrame",{"id":self.frame_source,
                "mode":self.mode,"speed":self.speed,"rect":self.rect,"anchor":{"x":self.origin[0],"y":self.origin[1]},
                "edge":self.edge,"points":self.sources})
        response = self.controller.state.core.call("frame", {
            "id":self.frame_source,"time":time,"opening":opening})
        self.progress = response["frame"]["progress"]
        self.alpha = response["frame"]["opacity"]
        self.points = response["points"]
        return response

    def finish_animation(self, closing):
        self.release_frame_source()
        self.frame, self.surface = 0, None
        self.progress = 0. if closing else 1.
        if closing:
            self.destroy()
        else:
            self.content.set_opacity(1)
            self.update_input_region()
            self.canvas.queue_draw()

    def release_frame_source(self):
        """Release cached geometry when an animation ends or is replaced."""
        if getattr(self,"frame_source",None):
            self.controller.state.core.call("releaseFrame",self.frame_source)
            self.frame_source = None

    def paint_mesh(self, context):
        rect = self.rect
        for y in range(8):
            for x in range(8):
                first = y * 9 + x
                for indices in ((first, first + 1, first + 9), (first + 1, first + 10, first + 9)):
                    source = [(self.sources[i]["x"] - rect["x"], self.sources[i]["y"] - rect["y"]) for i in indices]
                    target = [(self.points[i]["x"], self.points[i]["y"]) for i in indices]
                    self.paint_triangle(context, source, target)

    def paint_triangle(self, context, source, target):
        (sx, sy), (ux, uy), (vx, vy) = source
        (tx, ty), (ax, ay), (bx, by) = target
        det = (ux-sx)*(vy-sy) - (uy-sy)*(vx-sx)
        if abs(det) < .001:
            return
        xx = ((ax-tx)*(vy-sy) - (bx-tx)*(uy-sy))/det
        xy = ((bx-tx)*(ux-sx) - (ax-tx)*(vx-sx))/det
        yx = ((ay-ty)*(vy-sy) - (by-ty)*(uy-sy))/det
        yy = ((by-ty)*(ux-sx) - (ay-ty)*(vx-sx))/det
        if abs(xx*yy - xy*yx) < .0001:
            return
        context.save()
        context.move_to(*target[0])
        context.line_to(*target[1]); context.line_to(*target[2]); context.close_path()
        context.set_antialias(cairo.ANTIALIAS_NONE)
        context.clip()
        context.transform(cairo.Matrix(xx, yx, xy, yy, tx-xx*sx-xy*sy, ty-yx*sx-yy*sy))
        context.set_source_surface(self.surface)
        context.paint_with_alpha(self.alpha)
        context.restore()

    def draw(self, widget, context):
        if not self.group or self.loading:
            return False
        if self.surface:
            self.paint_mesh(context)
        else:
            context.translate(self.rect["x"], self.rect["y"])
            self.paint_background(context, self.rect["width"], self.rect["height"])
        return False

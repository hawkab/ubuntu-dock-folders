# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Paint portable preview commands and animation triangles with Cairo."""

import math
import cairo
import gi
gi.require_version("GioUnix", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GioUnix, GLib, Gtk, Pango, PangoCairo
from folder_preview import rounded, color


class PreviewPaint:
    """Cache native icons; paint scenes or a deformed card surface."""

    def __init__(self, widget):
        self.widget, self.icons = widget, {}

    def icon(self, app):
        desktop=app.get("desktop",app.get("icon",""))
        scale=max(1,self.widget.get_scale_factor())
        key=(desktop,scale)
        if key not in self.icons:
            try:
                info=GioUnix.DesktopAppInfo.new(desktop)
            except (GLib.Error,TypeError):
                info=None
            gicon=info.get_icon() if info else Gio.ThemedIcon.new(app.get("icon","application-x-executable"))
            theme=Gtk.IconTheme.get_for_display(self.widget.get_display())
            paintable=theme.lookup_by_gicon(gicon or Gio.ThemedIcon.new("application-x-executable"),96,scale,
                Gtk.TextDirection.NONE,Gtk.IconLookupFlags.FORCE_REGULAR)
            file=paintable.get_file() if paintable else None
            try:
                self.icons[key]=GdkPixbuf.Pixbuf.new_from_stream_at_scale(file.read(None),96*scale,96*scale,True,None) if file else None
            except GLib.Error:
                self.icons[key]=None
        return self.icons[key]

    def commands(self, context, commands):
        for item in commands:
            context.save()
            size=item.get("size",item.get("width",0))
            if item.get("rotation"):
                cx,cy=item["x"]+size/2,item["y"]+size/2
                context.translate(cx,cy);context.rotate(math.radians(item["rotation"]));context.translate(-cx,-cy)
            kind=item["type"]
            if kind in ("round","circle"):
                color(context,item["color"],item["alpha"])
                if kind=="round":rounded(context,item["x"],item["y"],item["width"],item["height"],item["radius"])
                else:context.arc(item["x"],item["y"],item["radius"],0,math.tau)
                context.fill()
            elif kind=="icon":
                pixbuf=self.icon(item["app"])
                if pixbuf:
                    context.translate(item["x"],item["y"])
                    context.scale(size/pixbuf.get_width(),size/pixbuf.get_height())
                    Gdk.cairo_set_source_pixbuf(context,pixbuf,0,0);context.paint_with_alpha(item["alpha"])
            elif kind=="text":
                layout=PangoCairo.create_layout(context)
                font=Pango.FontDescription.from_string("Sans")
                font.set_absolute_size(size*Pango.SCALE);layout.set_font_description(font)
                layout.set_width(round(item["width"]*Pango.SCALE));layout.set_ellipsize(Pango.EllipsizeMode.END)
                layout.set_alignment(Pango.Alignment.CENTER);layout.set_text(item["value"],-1)
                color(context,item["color"]);context.move_to(item["x"],item["y"]);PangoCairo.show_layout(context,layout)
            context.restore()

    def surface(self, scene, width, height):
        scale=max(1,self.widget.get_scale_factor())
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width*scale,height*scale)
        surface.set_device_scale(scale,scale)
        self.commands(cairo.Context(surface),scene["commands"])
        return surface

    def mesh(self, context, surface, frame):
        for triangle in frame["triangles"]:
            context.save()
            first,*rest=triangle["points"]
            context.move_to(first["x"],first["y"])
            for point in rest:context.line_to(point["x"],point["y"])
            context.close_path();context.set_antialias(cairo.ANTIALIAS_NONE);context.clip()
            context.transform(cairo.Matrix(*triangle["matrix"]))
            context.set_source_surface(surface);context.paint_with_alpha(frame["opacity"])
            context.restore()

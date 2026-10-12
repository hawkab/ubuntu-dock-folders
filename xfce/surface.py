# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Cache the backdrop once per opening and paint the folder surface."""

import cairo
from gi.repository import Gdk, GdkPixbuf, GLib
from drawing import rounded, color
from backdrop import capture_async


class PopupSurface:
    def capture_background(self, width, height, ready):
        wallpaper = self.group.get("wallpaper")
        glass = self.appearance["glass"]
        self.background, self.wallpaper = None, None
        def captured_background(captured):
            self.capture_job = None
            if self.controller.popup is not self or self.closing:
                return
            try:
                if captured:
                    sample = captured.scale_simple(8,8,GdkPixbuf.InterpType.BILINEAR)
                    pixels = sample.get_pixels()
                    count = sample.get_n_channels()
                    rgb = [sum(pixels[y*sample.get_rowstride()+x*count+c] for x in range(8) for y in range(8)) // 64 for c in range(3)]
                    self.backdrop = "#" + "".join(f"{channel:02x}" for channel in rgb)
                    self.update_contrast()
                    if glass:
                        self.background = self.frosted(captured,width,height,self.appearance["blurAmount"])
            except (GLib.Error, OSError, ValueError):
                pass
            self.load_wallpaper(width,height,wallpaper,glass)
            ready()
        if glass or not wallpaper:
            x,y = self.position
            self.capture_job = capture_async(x+self.rect["x"],y+self.rect["y"],width,height,
                self.controller.native,captured_background)
        else:
            captured_background(None)

    def load_wallpaper(self, width, height, wallpaper, glass):
        if wallpaper:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(wallpaper, width, height, False)
                self.wallpaper = self.frosted(pixbuf, width, height, .65 * self.appearance["blurAmount"]) if glass else pixbuf
            except (GLib.Error, OSError, ValueError):
                pass

    def frosted(self, pixbuf, width, height, amount=1):
        """Return a cached-size blurred pixbuf, or None when capture fails."""
        if pixbuf is None:
            return None
        try:
            from PIL import Image, ImageFilter

            channels = "RGBA" if pixbuf.get_has_alpha() else "RGB"
            radius = self.controller.state.contract["layout"]["blurRadius"] * amount
            reduction = max(1, int(radius / 8))
            pixbuf = pixbuf.scale_simple(max(1,width//reduction),max(1,height//reduction),GdkPixbuf.InterpType.BILINEAR)
            image = Image.frombytes(channels, (pixbuf.get_width(), pixbuf.get_height()),
                pixbuf.get_pixels(), "raw", channels, pixbuf.get_rowstride())
            image = image.filter(ImageFilter.GaussianBlur(radius/reduction)).resize((width, height)).convert("RGBA")
            return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(image.tobytes()),
                GdkPixbuf.Colorspace.RGB, True, 8, width, height, width*4)
        except (GLib.Error, OSError, ValueError):
            return None

    def paint_layer(self, context, pixbuf, width, height, opacity):
        if pixbuf is None or opacity <= 0:
            return
        context.save()
        context.scale(width/pixbuf.get_width(), height/pixbuf.get_height())
        Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
        context.paint_with_alpha(opacity)
        context.restore()

    def paint_background(self, context, width, height):
        appearance = self.appearance
        radius = self.controller.state.contract["layout"]["radius"]
        blend = appearance["blurAmount"]
        opacity = appearance["backgroundOpacity"]
        context.save()
        rounded(context, 1, 1, width-2, height-2, radius)
        context.clip()
        self.paint_layer(context, self.background, width, height, 1)
        context.set_source_rgba(*color(appearance["popupColor"], opacity))
        context.paint()
        self.paint_layer(context, self.wallpaper, width, height, opacity * (1 - .2 * appearance["blurAmount"]))
        sheen = cairo.LinearGradient(0, 0, 0, height)
        sheen.add_color_stop_rgba(0, 1, 1, 1, (.02 + .18 * blend) * opacity)
        sheen.add_color_stop_rgba(1, 1, 1, 1, .02 * blend * opacity)
        context.set_source(sheen); context.paint()
        context.restore()
        rounded(context, 1, 1, width-2, height-2, radius)
        context.set_source_rgba(1, 1, 1, (.08 + .22 * blend) * opacity)
        context.set_line_width(1); context.stroke()

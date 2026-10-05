# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Small GTK previews using the folder's real application icons."""

import math

import cairo
import gi
from PIL import Image, ImageFilter

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GioUnix, GLib, Gtk, Pango, PangoCairo
from i18n import _


def rounded(cr, x, y, width, height, radius):
    cr.new_sub_path()
    for cx, cy, start in (
        (x + width - radius, y + radius, -math.pi / 2),
        (x + width - radius, y + height - radius, 0),
        (x + radius, y + height - radius, math.pi / 2),
        (x + radius, y + radius, math.pi),
    ):
        cr.arc(cx, cy, radius, start, start + math.pi / 2)
    cr.close_path()


def color(cr, value, alpha=1):
    rgba = Gdk.RGBA()
    if not rgba.parse(value):
        rgba.parse("#26262a")
    cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, alpha)


def text(cr, value, x, y, width, size=10, bold=False, foreground="#ffffff"):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(
        Pango.FontDescription.from_string(f"Sans {'Bold ' if bold else ''}{size}")
    )
    layout.set_width(round(width * Pango.SCALE))
    layout.set_ellipsize(Pango.EllipsizeMode.END)
    layout.set_alignment(Pango.Alignment.CENTER)
    layout.set_text(value, -1)
    color(cr, foreground)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)


class FolderPreview(Gtk.DrawingArea):
    def __init__(self, group, mode, glass=False, font_size=10):
        super().__init__(hexpand=True, content_height=168)
        self.group = group
        self.mode = mode
        self.glass = glass
        self.font_size = font_size
        self.icons = {}
        self.wallpaper = (None, None)
        self.backdrop_cache = None
        self.set_draw_func(self.draw)
        self.set_tooltip_text(_("Icon preview") if mode == "dock" else _("Open folder preview"))

    def update(self, group):
        self.group = group
        self.queue_draw()

    def icon(self, entry):
        desktop = entry["desktop"]
        if desktop not in self.icons:
            info = GioUnix.DesktopAppInfo.new(desktop)
            gicon = info.get_icon() if info else Gio.ThemedIcon.new("application-x-executable")
            theme = Gtk.IconTheme.get_for_display(self.get_display())
            paintable = theme.lookup_by_gicon(
                gicon, 64, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.FORCE_REGULAR
            )
            file = paintable.get_file() if paintable else None
            try:
                self.icons[desktop] = (
                    GdkPixbuf.Pixbuf.new_from_stream_at_scale(file.read(None), 64, 64, True, None)
                    if file
                    else None
                )
            except GLib.Error:
                self.icons[desktop] = None
        return self.icons[desktop]

    def paint_icon(self, cr, entry, x, y, size):
        pixbuf = self.icon(entry)
        if not pixbuf:
            return
        cr.save()
        cr.translate(x, y)
        cr.scale(size / pixbuf.get_width(), size / pixbuf.get_height())
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()
        cr.restore()

    def draw(self, _area, cr, width, height):
        cr.save()
        rounded(cr, 0, 0, width, height, 16)
        cr.clip()
        self.draw_backdrop(cr, width, height)
        if self.mode == "dock":
            self.draw_dock(cr, width, height)
        else:
            self.draw_popup(cr, width, height)
        cr.restore()

    def draw_backdrop(self, cr, width, height):
        gradient = cairo.LinearGradient(0, height, width, 0)
        gradient.add_color_stop_rgb(0, 0.16, 0.23, 0.29)
        gradient.add_color_stop_rgb(0.5, 0.22, 0.20, 0.29)
        gradient.add_color_stop_rgb(1, 0.32, 0.21, 0.27)
        cr.set_source(gradient)
        cr.paint()
        glow = cairo.RadialGradient(
            width * 0.22, height * 0.8, 0, width * 0.22, height * 0.8, width * 0.55
        )
        glow.add_color_stop_rgba(0, 0.27, 0.56, 0.53, 0.35)
        glow.add_color_stop_rgba(1, 0.27, 0.56, 0.53, 0)
        cr.set_source(glow)
        cr.paint()
        rounded(cr, width * 0.55, 25, width * 0.5, height * 0.65, 12)
        cr.set_source_rgba(0.58, 0.72, 0.79, 0.25)
        cr.fill()
        cr.set_line_width(3)
        for y in range(48, 120, 14):
            cr.set_source_rgba(0.88, 0.9, 0.91, 0.38)
            cr.move_to(width * 0.60, y)
            cr.line_to(width * 0.87, y)
            cr.stroke()
        cr.set_source_rgba(0.59, 0.26, 0.36, 0.5)
        cr.arc(width * 0.22, height * 0.65, height * 0.4, 0, math.tau)
        cr.fill()

    def blurred_backdrop(self, width, height):
        if self.backdrop_cache and self.backdrop_cache[:2] == (width, height):
            return self.backdrop_cache[2]
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        self.draw_backdrop(cairo.Context(surface), width, height)
        surface.flush()
        image = Image.frombuffer(
            "RGBA", (width, height), surface.get_data(), "raw", "BGRA", surface.get_stride(), 1
        ).filter(ImageFilter.GaussianBlur(14))
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(image.tobytes()),
            GdkPixbuf.Colorspace.RGB,
            True,
            8,
            width,
            height,
            width * 4,
        )
        self.backdrop_cache = (width, height, pixbuf)
        return pixbuf

    def draw_dock(self, cr, width, height):
        group = self.group
        rounded(cr, width / 2 - 55, 10, 110, height - 20, 20)
        cr.set_source_rgba(0.03, 0.04, 0.06, 0.5)
        cr.fill()
        size = 72
        x, y = width / 2 - size / 2, 35
        opacity = group.get(
            "dockOpacity",
            (0 if group["transparentDock"] else 1) if "transparentDock" in group else 0.2,
        )
        cr.arc(x + size / 2, y + size / 2, size / 2, 0, math.tau)
        color(cr, group.get("dockColor", group["colors"][1]), opacity)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, opacity * 0.25)
        cr.set_line_width(1)
        cr.stroke()
        apps = group["apps"][:4]
        positions = {
            1: ((0.5, 0.5),),
            2: ((0.22, 0.5), (0.78, 0.5)),
            3: ((0.25, 0.27), (0.75, 0.27), (0.5, 0.79)),
        }.get(len(apps), ((0.24, 0.24), (0.76, 0.24), (0.24, 0.76), (0.76, 0.76)))
        icon_size = size * (0.52 if len(apps) == 2 else 0.48)
        for entry, (px, py) in zip(apps, positions):
            self.paint_icon(
                cr, entry, x + size * px - icon_size / 2, y + size * py - icon_size / 2, icon_size
            )
        if group.get("showLabel", False):
            text(cr, group["name"], width / 2 - 51, 116, 102, size=self.font_size * 0.75)

    def draw_popup(self, cr, width, height):
        group = self.group
        apps = group["apps"][:4]
        card_width = min(width - 40, max(240, len(apps) * 100 + 36))
        x, y = (width - card_width) / 2, 12
        opacity = group.get("glassOpacity", 0.38) if self.glass else group.get("popupOpacity", 0.98)
        background = group.get("popupColor", "#26262a")
        rounded(cr, x, y + 5, card_width, height - 24, 20)
        cr.set_source_rgba(0, 0, 0, 0.16 * opacity)
        cr.fill()
        if self.glass:
            cr.save()
            rounded(cr, x, y, card_width, height - 24, 20)
            cr.clip()
            Gdk.cairo_set_source_pixbuf(cr, self.blurred_backdrop(width, height), 0, 0)
            cr.paint()
            cr.restore()
        rounded(cr, x, y, card_width, height - 24, 20)
        color(cr, background, opacity)
        cr.fill()
        filename = group.get("wallpaper")
        if filename != self.wallpaper[0]:
            try:
                pixbuf = (
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(filename, 640, 320, True)
                    if filename
                    else None
                )
            except GLib.Error:
                pixbuf = None
            self.wallpaper = (filename, pixbuf)
        pixbuf = self.wallpaper[1]
        if pixbuf:
            cr.save()
            rounded(cr, x, y, card_width, height - 24, 20)
            cr.clip()
            scale = max(card_width / pixbuf.get_width(), (height - 24) / pixbuf.get_height())
            cr.translate(
                x + (card_width - pixbuf.get_width() * scale) / 2,
                y + (height - 24 - pixbuf.get_height() * scale) / 2,
            )
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
            cr.paint_with_alpha(opacity)
            cr.set_source_rgba(0, 0, 0, 0.42 * opacity)
            cr.paint()
            cr.restore()
        rgba = Gdk.RGBA()
        rgba.parse(background)
        light = (
            not pixbuf and rgba.red * 0.2126 + rgba.green * 0.7152 + rgba.blue * 0.0722 > 160 / 255
        )
        foreground = "#202124" if light else "#ffffff"
        text(
            cr,
            group["name"],
            x + 20,
            y + 12,
            card_width - 40,
            size=11,
            bold=True,
            foreground=foreground,
        )
        cell = (card_width - 28) / max(1, len(apps))
        for index, entry in enumerate(apps):
            center = x + 14 + cell * (index + 0.5)
            self.paint_icon(cr, entry, center - 20, y + 45, 40)
            text(
                cr,
                entry.get("label", "").replace("\n", " "),
                center - cell / 2 + 3,
                y + 96,
                cell - 6,
                size=9,
                foreground=foreground,
            )

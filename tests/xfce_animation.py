# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check live Xfce transitions against the steady card and focus behavior."""

from gi.repository import Gdk, Gtk
from PIL import Image, ImageChops, ImageStat


def capture(popup):
    pixbuf = Gdk.pixbuf_get_from_window(popup.window.get_window(), popup.rect["x"], popup.rect["y"],
                                      popup.rect["width"], popup.rect["height"])
    channels = "RGBA" if pixbuf.get_has_alpha() else "RGB"
    return Image.frombytes(channels, (pixbuf.get_width(), pixbuf.get_height()), bytes(pixbuf.get_pixels()),
                           "raw", channels, pixbuf.get_rowstride()).convert("RGB")


def check_animations(controller, key, settings, wait, settle):
    """Open and close each registered mode, then activate another application."""
    for mode in ("none", "fade", "scale", "flow", "lamp", "fold", "sheet", "unfold"):
        controller.popup.close(False)
        settings.set_string("animation", mode)
        settings.set_int("animation-speed", 200)
        settle(.05)
        controller.toggle(controller.state.groups[key], controller.buttons["local.groups.test.desktop"])
        wait(lambda: controller.popup and controller.popup.frame == 0)
        popup = controller.popup
        assert popup.progress == 1
        popup.snapshot()
        popup.mode, popup.speed = mode, 200
        popup.animation_frame(1, True)
        popup.canvas.queue_draw()
        settle(.05)
        endpoint = capture(popup)
        popup.finish_animation(False)
        settle(.05)
        steady = capture(popup)
        difference = sum(ImageStat.Stat(ImageChops.difference(endpoint, steady)).mean)/3
        assert difference < 1, (mode, difference)
        if mode != "none":
            popup.animate(False)
            wait(lambda: popup.progress > .1 and popup.progress < .95)
            assert popup.surface and len(popup.points) == 81
            wait(lambda: popup.frame == 0)
        popup.close()
        wait(lambda: controller.popup is None)
        controller.toggle(controller.state.groups[key], controller.buttons["local.groups.test.desktop"])
        wait(lambda: controller.popup and controller.popup.frame == 0)
    window = Gtk.Window(title="Focus transfer")
    window.show_all(); window.present()
    wait(lambda: controller.popup is None)
    window.destroy()
    settle(.1)
    controller.toggle(controller.state.groups[key], controller.buttons["local.groups.test.desktop"])
    wait(lambda: controller.popup and controller.popup.frame == 0)
    print("Xfce: all eight transitions, endpoint continuity and focus loss passed.")

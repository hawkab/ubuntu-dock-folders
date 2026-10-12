# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Drive real pointer gestures only inside the tagged X11 test display."""

import ctypes
import math
import os
from gi.repository import GLib


class Pointer:
    def __init__(self):
        assert os.environ.get("DOCK_FOLDERS_TEST_SESSION")
        self.xlib = ctypes.CDLL("libX11.so.6")
        self.xtest = ctypes.CDLL("libXtst.so.6")
        self.xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.xlib.XOpenDisplay.restype = ctypes.c_void_p
        self.xlib.XFlush.argtypes = [ctypes.c_void_p]
        self.xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.xtest.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        self.xtest.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.display = self.xlib.XOpenDisplay(os.environ["DISPLAY"].encode())
        assert self.display
        self.dragging = False

    def point(self, button):
        glyph = button.get_child().get_children()[0]
        toplevel = button.get_toplevel()
        origin = toplevel.get_window().get_origin()
        x, y = glyph.translate_coordinates(toplevel, glyph.get_allocated_width()//2, glyph.get_allocated_height()//2)
        return origin[-2]+x, origin[-1]+y

    def move(self, x, y):
        self.xtest.XTestFakeMotionEvent(self.display, -1, int(x), int(y), 0)
        self.xlib.XFlush(self.display)

    def button(self, down):
        self.xtest.XTestFakeButtonEvent(self.display, 1, int(down), 0)
        self.xlib.XFlush(self.display)

    def click(self, point):
        self.move(*point);self.button(True)
        GLib.timeout_add(80, lambda: (self.button(False), GLib.SOURCE_REMOVE)[1])

    def drag(self, source, destination):
        start = self.point(source)
        distance = max(1,math.hypot(destination[0]-start[0],destination[1]-start[1]))
        self.move(*start);self.button(True)
        step = 0
        self.dragging = True
        def tick():
            nonlocal step
            step += 1
            initial = min(.5,12/distance)
            fraction = initial*step/3 if step<=3 else initial+(1-initial)*(step-3)/13
            fraction = min(1.,fraction)
            self.move(start[0]+(destination[0]-start[0])*fraction,
                      start[1]+(destination[1]-start[1])*fraction)
            if fraction < 1:return GLib.SOURCE_CONTINUE
            self.button(False);self.dragging = False
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(20,tick)

    def close(self):
        self.xlib.XCloseDisplay(self.display)


def check_gestures(controller, window, wait, settle):
    settings = controller.state.settings
    groups, favorites = settings.get_string("groups"), settings.get_strv("xfce-favorites")
    sizes = {key: settings.get_int(key) for key in ("group-icon-size", "mini-icon-size")}
    settings.set_int("group-icon-size", 200)
    settings.set_int("mini-icon-size", 300)
    settings.set_string("groups", "{}")
    settings.set_strv("xfce-favorites", [f"test.{name}.desktop" for name in ("one", "two", "three")])
    settings.apply()
    panel_window=getattr(controller,"test_host",controller.window)
    panel_window.set_keep_above(True);panel_window.move(120,650)
    settle()
    pointer = Pointer()
    pointer.drag(controller.buttons["test.one.desktop"], pointer.point(controller.buttons["test.two.desktop"]))
    wait(lambda: len(controller.state.groups)==1 and not pointer.dragging)
    settle()
    group = next(iter(controller.state.groups.values()))
    assert len(group["apps"])==2
    desktop = group["id"]+".desktop"
    pointer.drag(controller.buttons["test.three.desktop"], pointer.point(controller.buttons[desktop]))
    wait(lambda: len(next(iter(controller.state.groups.values()))["apps"])==3 and not pointer.dragging)
    settle()
    def open_folder():
        pointer.click(pointer.point(controller.buttons[desktop]))
        wait(lambda: controller.popup and not controller.popup.frame)
    open_folder()
    width = controller.popup.rect["width"]
    x,y = pointer.point(controller.buttons[desktop])
    pointer.click((x,y-8))
    wait(lambda: controller.popup is None)
    open_folder()
    pointer.click((1050,400))
    wait(lambda: controller.popup is None)
    open_folder()
    source = controller.popup.grid.get_children()[0]
    pointer.drag(source,(1000,600))
    wait(lambda: len(next(iter(controller.state.groups.values()))["apps"])==2 and not pointer.dragging)
    settle()
    assert controller.popup and controller.popup.rect["width"] < width
    assert len(controller.state.favorites)==2
    pointer.drag(controller.popup.grid.get_children()[0],(1000,600))
    wait(lambda: not controller.state.groups and not controller.popup and not pointer.dragging)
    settle()
    pointer.drag(controller.buttons["test.one.desktop"],pointer.point(controller.buttons["test.two.desktop"]))
    wait(lambda: len(controller.state.groups)==1 and not pointer.dragging)
    settle()
    assert len(next(iter(controller.state.groups.values()))["apps"])==2
    settings.set_strv("xfce-favorites",controller.state.favorites+["test.four.desktop"])
    settle()
    pointer.drag(controller.buttons["test.three.desktop"],pointer.point(controller.buttons["test.four.desktop"]))
    wait(lambda: len(controller.state.groups)==2 and not pointer.dragging)
    settle()
    keys=list(controller.state.groups)
    for key in keys + keys[::-1] + keys:
        target=controller.state.groups[key]["id"]+".desktop"
        if controller.popup and controller.popup.key==key:
            continue
        previous=controller.popup
        pointer.click(pointer.point(controller.buttons[target]))
        wait(lambda: controller.popup and controller.popup.key==key and not controller.popup.frame)
        if previous:
            assert not previous.window.get_visible()
        settle(.15)
        assert controller.popup and controller.popup.key==key
    pointer.click(pointer.point(controller.popup.anchor))
    wait(lambda: controller.popup is None)
    pointer.close()
    settings.set_string("groups",groups);settings.set_strv("xfce-favorites",favorites)
    for key, value in sizes.items():
        settings.set_int(key, value)
    settings.apply()
    settle()
    panel_window.set_keep_above(False)
    print("Xfce: pointer grouping, extraction, regrouping, one-click folder switching, compact resize and dismissal passed.")

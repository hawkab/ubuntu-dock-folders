# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check installed panel gestures using opaque fixture icons in a private display."""

import json
import os
import time
from PIL import Image, ImageChops, ImageGrab
from xfce_pointer import Pointer

COLORS = {"terminal": (245, 15, 25), "files": (15, 235, 35),
          "calculator": (15, 25, 245), "four": (245, 215, 15)}


def check_installed(settings, wait, pointer=None, screenshot=None):
    groups, favorites = settings.get_string("groups"), settings.get_strv("xfce-favorites")
    sizes = {key: settings.get_int(key) for key in ("group-icon-size", "mini-icon-size")}
    pointer = pointer or Pointer()
    screenshot = screenshot or (lambda: ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).convert("RGB"))

    def points(dock=True):
        image = screenshot()
        result = {}
        for name, color in COLORS.items():
            mask = ImageChops.difference(image, Image.new("RGB", image.size, color))
            mask = mask.convert("L").point(lambda value: 255 if value == 0 else 0)
            edge = image.height-98
            zone = (0, edge, image.width, image.height) if dock else (0, 0, image.width, edge)
            bbox = mask.crop(zone).getbbox()
            if bbox:
                result[name] = ((bbox[0]+bbox[2])/2, zone[1]+(bbox[1]+bbox[3])/2)
        return result

    def drag(source, target):
        pointer.move(*source)
        time.sleep(.1)
        pointer.button(True)
        for step in range(1, 25):
            fraction = step / 24
            pointer.move(*(source[i] + (target[i]-source[i])*fraction for i in (0, 1)))
            time.sleep(.025)
        pointer.button(False)

    def click(names):
        position = points()
        x, y = (sum(position[name][i] for name in names)/len(names) for i in (0, 1))
        pointer.move(x, y)
        time.sleep(.12)
        pointer.button(True)
        time.sleep(.08)
        pointer.button(False)

    try:
        settings.set_int("group-icon-size", 200)
        settings.set_int("mini-icon-size", 300)
        wait(lambda: {"terminal", "files"} <= points().keys(), "Fixture folder did not map")
        time.sleep(.4)
        click(("terminal", "files"))
        wait(lambda: "terminal" in points(False), "Installed folder did not open")
        time.sleep(.3)
        image = screenshot()
        drag(points(False)["terminal"], (image.width-100, image.height-24))
        wait(lambda: settings.get_string("groups") == "{}", "Extraction did not dissolve the installed folder")
        wait(lambda: not points(False), "Dissolved folder left its popup visible")
        time.sleep(.3)
        position = points()
        drag(position["terminal"], position["files"])
        wait(lambda: len(json.loads(settings.get_string("groups"))) == 1, "Installed icons could not regroup")
        settings.set_strv("xfce-favorites", settings.get_strv("xfce-favorites") +
                          ["test.calculator.desktop", "test.four.desktop"])
        wait(lambda: {"calculator", "four"} <= points().keys(), "Second fixture did not map")
        time.sleep(.3)
        position = points()
        drag(position["calculator"], position["four"])
        wait(lambda: len(json.loads(settings.get_string("groups"))) == 2, "Second installed folder was not created")
        for names in (("terminal", "files"), ("calculator", "four")) * 2:
            time.sleep(.3)
            click(names)
            wait(lambda: set(points(False)) == set(names), "One click did not switch the installed folder")
        click(names)
        wait(lambda: not points(False), "Clicking the current folder did not close it")
        print("Native Xfce: maximum-size extraction, regrouping and one-click folder switching passed")
    finally:
        pointer.button(False)
        pointer.close()
        settings.set_string("groups", groups)
        settings.set_strv("xfce-favorites", favorites)
        for key, value in sizes.items():
            settings.set_int(key, value)
        time.sleep(.5)

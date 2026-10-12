# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check native window indicators, focus, backdrop blur and launcher deletion."""

import json
import os
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from wayland_pointer import Pointer
from xfce_native_pointer import COLORS

ROOT = Path(__file__).resolve().parent.parent


def check(settings, panel, wait, screenshot):
    application = subprocess.Popen(["/usr/bin/python3", str(ROOT / "tests/native_window.py")])
    image = screenshot()
    pointer = Pointer(image.width,image.height)
    edge = image.height-98

    def mask(image, color):
        return ImageChops.difference(image, Image.new("RGB", image.size, color)).convert("L").point(
            lambda value: 255 if value == 0 else 0)

    def opened():
        return mask(screenshot(),COLORS["terminal"]).crop((0,0,image.width,edge)).getbbox()

    def click(x,y):
        pointer.move(x,y)
        time.sleep(.12)
        pointer.button(True)
        time.sleep(.08)
        pointer.button(False)

    def toggle():
        screen = screenshot()
        positions = []
        for name in ("terminal","files"):
            box = mask(screen,COLORS[name]).crop((0,edge,screen.width,screen.height)).getbbox()
            positions.append(((box[0]+box[2])/2,edge+(box[1]+box[3])/2))
        click(*(sum(point[i] for point in positions)/2 for i in (0,1)))

    try:
        wait(lambda: mask(screenshot(),(166,220,71)).crop((0,edge,image.width,image.height)).getbbox(),
             "Native Wayland window did not update its running indicator")
        def panel_icon():
            return mask(screenshot(),COLORS["terminal"]).crop((0,edge,image.width,image.height)).getbbox()
        pointer.move(image.width-30,30)
        settings.set_int("orbit-speed",-90)
        time.sleep(.35)
        first=panel_icon()
        time.sleep(.25)
        assert panel_icon()!=first, "Native Wayland continuous orbit did not move"
        settings.set_int("orbit-speed",0)
        settings.set_int("hover-orbit-speed",-180)
        time.sleep(1.7)
        screen=screenshot()
        boxes=[mask(screen,COLORS[name]).crop((0,edge,image.width,image.height)).getbbox() for name in ("terminal","files")]
        pointer.move(sum((box[0]+box[2])/2 for box in boxes)/2,edge+sum((box[1]+box[3])/2 for box in boxes)/2)
        time.sleep(.25)
        first=panel_icon()
        time.sleep(.25)
        assert panel_icon()!=first, "Native Wayland hover orbit did not move"
        pointer.move(image.width-30,30)
        time.sleep(1.7)
        first=panel_icon()
        time.sleep(.2)
        assert panel_icon()==first, "Native Wayland orbit continued after pointer leave"
        settings.set_int("hover-orbit-speed",0)
        time.sleep(.3)
        print("Xfce/Wayland: counterclockwise continuous and hover-only orbit and pointer leave passed")
        toggle()
        wait(opened,"Native folder did not open over the application")
        time.sleep(.35)
        assert opened(), "Native folder closed while opening"
        icon = opened()
        pointer.move((icon[0]+icon[2])/2,(icon[1]+icon[3])/2)
        def chooser():
            box = opened()
            return box and box[2]-box[0] >= 90
        wait(chooser, "Native window chooser did not open on hover")
        click(image.width-100,100)
        wait(lambda: not opened(),"Native folder did not close on focus loss")
        groups = json.loads(settings.get_string("groups"))
        groups["saved"].update(popupTransparency=95, blurStrength=0)
        settings.set_string("groups",json.dumps(groups))
        time.sleep(.4)
        toggle()
        wait(opened,"Unblurred native folder did not open")
        time.sleep(.3)
        sharp = screenshot()
        toggle()
        wait(lambda: not opened(),"Native folder did not close")
        groups["saved"]["blurStrength"] = 100
        settings.set_string("groups",json.dumps(groups))
        time.sleep(.4)
        toggle()
        wait(opened,"Blurred native folder did not open")
        time.sleep(.3)
        blurred = screenshot()
        icons = mask(blurred,COLORS["terminal"]).crop((0,0,image.width,edge)).getbbox()
        patch = (icons[0],icons[1]-24,icons[2],icons[1]-8)
        sharpness = ImageStat.Stat(sharp.crop(patch)).stddev[0]
        softness = ImageStat.Stat(blurred.crop(patch)).stddev[0]
        assert sharpness > 30 and softness < sharpness*.6, (sharpness,softness,patch)
        output = ROOT.parent / "xfce-wayland-review"
        output.mkdir(exist_ok=True)
        sharp.save(output / "blur-0.png")
        blurred.save(output / "blur-100.png")
        (Path(os.environ["XDG_DATA_HOME"])/"applications/test.terminal.desktop").unlink()
        wait(lambda: "test.terminal.desktop" not in settings.get_string("groups"),
             "Deleted application survived reconciliation")
        wait(lambda: not opened(),"Deleted folder left its native window open")
        def ticks():
            fields = Path(f"/proc/{panel.pid}/stat").read_text().rsplit(")",1)[1].split()
            return int(fields[11])+int(fields[12])
        before = ticks()
        time.sleep(1.2)
        assert ticks()-before < os.sysconf("SC_CLK_TCK")*.3, "Panel remained busy after launcher removal"
        print("Xfce/Wayland: native window indicator, focus loss, measured backdrop blur and live deletion passed")
    finally:
        pointer.button(False)
        pointer.close()
        application.terminate()
        application.wait(timeout=3)

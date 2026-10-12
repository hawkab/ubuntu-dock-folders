# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise the X11 backend against real windows and removed desktop files."""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build/xfce"))
from panel import Controller, Gdk, GLib, Gtk
from state import FolderState


def wait(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError("Xfce condition did not settle")


def settle(seconds=.35):
    end = time.monotonic() + seconds
    wait(lambda: time.monotonic() >= end, seconds + 1)


apps = Path(os.environ["XDG_DATA_HOME"]) / "applications"
apps.mkdir(parents=True, exist_ok=True)
for name in ("one", "two", "three", "four", "missing"):
    (apps / f"test.{name}.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName=Test {name}\nExec=true\n"
        f"Icon=utilities-terminal\nStartupWMClass=folder-test-{name}\n")
(apps / "test.missing.desktop").unlink()
initial = FolderState()
settings = initial.settings
group = {"id": "local.groups.test", "name": "Test folder", "icon": "folder",
         "colors": ["#40505c", "#263d4a"], "apps": [
             {"desktop": f"test.{name}.desktop", "label": name} for name in ("one", "two", "three", "missing")]}
settings.set_string("groups", json.dumps({"test": group}))
settings.set_strv("xfce-favorites", ["local.groups.test.desktop"])
settings.set_boolean("customization", True)
initial.close()
controller = Controller()
reader, writer = os.pipe()
with os.fdopen(reader, "r") as stream:
    os.write(writer, b"layout 40 0\nlayout 60 1\nlayout 48 0\n")
    assert controller.command(stream, GLib.IOCondition.IN) == GLib.SOURCE_CONTINUE
    assert (controller.size, controller.orientation) == (48, Gtk.Orientation.HORIZONTAL)
    os.write(writer, b"layout 6")
    controller.command(stream, GLib.IOCondition.IN)
    assert controller.size == 48
    os.write(writer, b"4 0\n")
    controller.command(stream, GLib.IOCondition.IN)
    assert controller.size == 64
    os.write(writer, b"layout 48 0\n")
    controller.command(stream, GLib.IOCondition.IN)
os.close(writer)
controller.window.set_skip_taskbar_hint(True)
wait(lambda: len(controller.state.groups["test"]["apps"]) == 3)
assert controller.state.favorites == ["local.groups.test.desktop"]
from xfce_hover import check_hover
check_hover(controller, "test", wait, settle)
window = Gtk.Window(title="Real test application")
window.set_wmclass("folder-test-one", "folder-test-one")
window.set_default_size(480, 300)
window.add(Gtk.Label(label="Window preview"))
start = time.monotonic()
window.show_all()
wait(lambda: controller.windows.get("test.one.desktop"))
assert time.monotonic() - start < 1.5
saved_group=json.loads(controller.state.settings.get_string("groups"))["test"]
from xfce_pointer import check_gestures
check_gestures(controller, window, wait, settle)
controller.embedded = True
for setting, values in (("group-icon-size", (80,120,200)), ("mini-icon-size", (80,230,300))):
    sizes=[]
    for value in values:
        settings.set_int(setting,value);settle()
        glyph=controller.buttons['local.groups.test.desktop'].get_child().get_children()[0]
        sizes.append(glyph.body if setting=='group-icon-size' else glyph.layout['size'])
    assert sizes[0] < sizes[1] < sizes[2], (setting,sizes)
controller.embedded = False
settings.set_int('group-icon-size',120);settings.set_int('mini-icon-size',230);settle()
assert controller.state.execute({"operation":"setFolderPinned","key":"test","pinned":False})
wait(lambda: "test.one.desktop" in controller.buttons and "local.groups.test.desktop" not in controller.buttons)
assert controller.state.execute({"operation":"setFolderPinned","key":"test","pinned":True})
wait(lambda: "local.groups.test.desktop" in controller.buttons and "test.one.desktop" not in controller.buttons)
assert json.loads(controller.state.settings.get_string("groups"))["test"]==saved_group
controller.toggle(controller.state.groups["test"], controller.buttons["local.groups.test.desktop"])
wait(lambda: controller.popup and controller.popup.frame == 0)
popup = controller.popup
assert popup.progress == 1
assert popup.rect["width"] >= 160
assert popup.rect["width"] < 300
assert controller.state.move("test.three.desktop", "test", "test.one.desktop")
wait(lambda: controller.state.groups["test"]["apps"][0]["desktop"] == "test.three.desktop")
settle()
assert controller.popup is popup
assert controller.state.undo is not None
controller.undo()
wait(lambda: controller.state.groups["test"]["apps"][0]["desktop"] == "test.one.desktop")
assert controller.popup is popup
controller.show_preview("test.one.desktop", popup.grid.get_children()[-1])
assert controller.preview.get_mapped()
controller.hide_preview()
controller.state.settings.set_int("blur-strength", 100)
settle()
popup.close(False)
controller.toggle(controller.state.groups["test"], controller.buttons["local.groups.test.desktop"])
wait(lambda: controller.popup and controller.popup.frame == 0)
assert controller.popup.background is not None
from PIL import Image
wallpaper = Path(os.environ["HOME"]) / "glass-wallpaper.png"
Image.new("RGB", (64,64), "#ff00ff").save(wallpaper)
controller.popup.close(False)
assert controller.state.execute({"operation":"appearance", "key":"test", "property":"wallpaper", "value":str(wallpaper)})
settle()
controller.toggle(controller.state.groups["test"], controller.buttons["local.groups.test.desktop"])
wait(lambda: controller.popup and controller.popup.frame == 0)
assert controller.popup.background is not None and controller.popup.wallpaper is not None
assert bytes(controller.popup.background.get_pixels()) != bytes(controller.popup.wallpaper.get_pixels()), "Wallpaper replaced the blurred desktop"
controller.popup.close(False)
assert controller.state.execute({"operation":"appearance", "key":"test", "property":"wallpaper", "value":""})
settle()
controller.toggle(controller.state.groups["test"], controller.buttons["local.groups.test.desktop"])
wait(lambda: controller.popup and controller.popup.frame == 0)
from xfce_animation import check_animations
check_animations(controller, "test", settings, wait, settle)
assert controller.state.extract("test.three.desktop")
settle()
assert "test.three.desktop" in controller.buttons
assert not controller.buttons["test.three.desktop"].get_child().get_children()[0].group
controller.state.move("test.three.desktop", "test")
settle()
(apps / "test.three.desktop").unlink()
wait(lambda: len(controller.state.groups["test"]["apps"]) == 2, 8)
assert controller.popup
assert not controller.state.move("test.three.desktop", "test")
count = controller.render_count
settle(1)
assert controller.render_count - count <= 1
controller.dragging = True
(apps / "test.two.desktop").unlink()
wait(lambda: "test" not in controller.state.groups, 8)
controller.drag_end()
settle()
assert controller.popup is None
assert controller.state.favorites == ["test.one.desktop"]
assert "test.one.desktop" in controller.buttons
window.destroy()
wait(lambda: not controller.windows.get("test.one.desktop"))
controller.window.destroy()
assert not controller.tracker.signals and not controller.tracker.records
assert controller.state.core.process.poll() == 0
for name in ("two", "three"):
    (apps / f"test.{name}.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName=Test {name}\nExec=true\nIcon=utilities-terminal\n")
from xfce_embedded import check_embedded
check_embedded(wait, settle)
print("Xfce/X11: startup cleanup, live window indicators, popup animation, reorder, undo, extraction, previews, glass, live removal and shutdown passed.")

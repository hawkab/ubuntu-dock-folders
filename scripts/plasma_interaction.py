# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Drive native pointer interactions in the isolated desktop."""

import ctypes
import json
import os
import time
from pathlib import Path
from probe_log import records

def interaction(output, connection, settings):
    import re
    from gi.repository import Gio, GLib

    x11 = ctypes.CDLL("libX11.so.6")
    xtest = ctypes.CDLL("libXtst.so.6")
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xtest.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
    xtest.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    display = x11.XOpenDisplay(os.environ["DISPLAY"].encode())

    def wait(predicate, timeout=4):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(.05)
        raise RuntimeError("Native panel interaction did not settle")

    def state():
        result = connection.call_sync("io.github.hawkab.DockFolders.Plasma", "/io/github/hawkab/DockFolders",
            "org.freedesktop.DBus.Properties", "Get", GLib.Variant("(ss)", ("io.github.hawkab.DockFolders.Plasma", "State")),
            None, Gio.DBusCallFlags.NONE, 3000, None)
        return json.loads(result.unpack()[0])

    def points():
        output.flush()
        found = records(output.name, "NATIVE_GEOMETRY")
        return found[-1] if found else {}

    def motion(point):
        xtest.XTestFakeMotionEvent(display, -1, round(point["x"]), round(point["y"]), 0)
        x11.XFlush(display)

    def hover_mode(value):
        script = "var w=panels()[0].widgets().filter(w=>w.type==='io.github.hawkab.DockFolders')[0];w.currentConfigGroup=['General'];w.writeConfig('hoverEffect',%d);w.writeConfig('hoverAngle',60);w.writeConfig('hoverSpeed',150);w.reloadConfig();" % value
        connection.call_sync("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript",
            GLib.Variant("(s)", (script,)), None, Gio.DBusCallFlags.NONE, 2000, None)
        wait(lambda: points().get("__hover", {}).get("mode") == value and points()["__hover"]["angle"] == 60)

    def edit(request):
        connection.call_sync("io.github.hawkab.DockFolders.Plasma", "/io/github/hawkab/DockFolders",
            "io.github.hawkab.DockFolders.Plasma", "Edit", GLib.Variant("(s)", (json.dumps(request),)),
            None, Gio.DBusCallFlags.NONE, 3000, None)

    def orbit_speeds(always, hovered):
        script = "var w=panels()[0].widgets().filter(w=>w.type==='io.github.hawkab.DockFolders')[0];w.currentConfigGroup=['General'];w.writeConfig('orbitSpeed',%d);w.writeConfig('hoverOrbitSpeed',%d);w.reloadConfig();" % (always,hovered)
        connection.call_sync("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript",
            GLib.Variant("(s)", (script,)), None, Gio.DBusCallFlags.NONE, 2000, None)

    def stack(value):
        request = {"operation":"appearance", "key":next(iter(state()["groups"])), "property":"alwaysStack", "value":value}
        connection.call_sync("io.github.hawkab.DockFolders.Plasma", "/io/github/hawkab/DockFolders",
            "io.github.hawkab.DockFolders.Plasma", "Edit", GLib.Variant("(s)", (json.dumps(request),)),
            None, Gio.DBusCallFlags.NONE, 3000, None)
        wait(lambda: points().get("__hover", {}).get("stacked") == value)

    def button(down):
        xtest.XTestFakeButtonEvent(display, 1, down, 0)
        x11.XFlush(display)

    def drag(source, target):
        motion(source)
        time.sleep(.1)
        button(1)
        for step in range(1, 25):
            motion({axis: source[axis] + (target[axis] - source[axis]) * step / 24 for axis in ("x", "y")})
            time.sleep(.015)
        button(0)

    try:
        wait(lambda: "test.terminal.desktop" in points())
        geometry = points()
        drag(geometry["test.terminal.desktop"], geometry["test.files.desktop"])
        wait(lambda: len(state()["groups"]) == 1)
        group = next(iter(state()["groups"].values()))
        desktop = group["id"] + ".desktop"
        wait(lambda: desktop in points() and len(points().get("__hover", {}).get("items", [])) == 2)
        time.sleep(.35)
        geometry = points()
        drag(geometry["test.calculator.desktop"], geometry[desktop])
        wait(lambda: len(next(iter(state()["groups"].values()))["apps"]) == 3)
        motion({"x":20,"y":20})
        wait(lambda: len(points().get("__hover", {}).get("items", [])) == 3)
        wait(lambda: points().get("__hover", {}).get("progress") == 0)
        resting = points()["__hover"]
        hover_mode(1)
        motion(points()[desktop])
        wait(lambda: points()["__hover"]["progress"] == 1)
        turned = points()["__hover"]
        assert turned["size"] == resting["size"] and turned["width"] == resting["width"]
        import math
        center = resting["body"] / 2 - resting["size"] / 2
        for initial, current in zip(resting["items"], turned["items"]):
            x, y = initial["x"]-center, initial["y"]-center
            assert abs(current["x"]-center-(x*math.cos(math.pi/3)-y*math.sin(math.pi/3)))<.01
            assert abs(current["y"]-center-(x*math.sin(math.pi/3)+y*math.cos(math.pi/3)))<.01
            assert abs(current["rotation"]-initial["rotation"]-60)<.01
        assert all(abs(after-before)<.01 for before,after in zip(resting["glyphAngles"],turned["glyphAngles"]))
        assert turned["duration"] == 120
        motion({"x":20,"y":20})
        wait(lambda: points()["__hover"]["progress"] == 0)
        assert points()["__hover"]["items"] == resting["items"]
        hover_mode(2)
        motion(points()[desktop])
        time.sleep(.5)
        assert points()["__hover"]["progress"] == 0 and points()["__hover"]["cards"] == 0
        assert points()["__hover"]["items"] == resting["items"], "Flat icons became cards"
        motion({"x":20,"y":20})
        stack(True)
        fan_rest = points()["__hover"]
        tooltip_offset = len(Path(output.name).read_text())
        motion(points()[desktop])
        wait(lambda: points()["__hover"]["progress"] == 1)
        fan = points()["__hover"]
        assert fan["cards"] == 1 and fan["items"] != resting["items"]
        assert fan["width"] > fan_rest["width"] and fan["height"] == fan_rest["height"]
        assert fan["width"] <= fan["body"]*2 + 1
        motion({"x":20,"y":20})
        wait(lambda: points()["__hover"]["progress"] == 0)
        hover_mode(3)
        motion(points()[desktop])
        wait(lambda: points()["__hover"]["progress"] == 1)
        combined = points()["__hover"]
        assert combined["size"] == fan["size"] and combined["width"] == fan["width"]
        for initial, current in zip(fan["items"], combined["items"]):
            assert abs(current["rotation"]-initial["rotation"]-60)<.01
        time.sleep(1)
        events = re.findall(r"NATIVE_TOOLTIP " + re.escape(desktop) + r" (true|false)", Path(output.name).read_text()[tooltip_offset:])
        assert events and events[-1] == "true" and len(events) <= 7, ("Tooltip flickered", events)
        button(1)
        button(0)
        wait(lambda: "test.terminal.desktop" in points())
        assert state()["groups"], "Hover changed persisted membership"
        geometry = points()
        drag(geometry["test.calculator.desktop"], geometry["test.files.desktop"])
        wait(lambda: next(iter(state()["groups"].values()))["apps"][0]["desktop"] == "test.calculator.desktop")
        time.sleep(.5)
        wait(lambda: "test.terminal.desktop" in points())
        geometry = points()
        const_dock = geometry["__dock"]
        drag(geometry["test.terminal.desktop"], {"x": const_dock["x"] + const_dock["width"] - 10, "y": const_dock["y"] + const_dock["height"] / 2})
        wait(lambda: "test.terminal.desktop" in state()["favorites"])
        from plasma_folder_switch import check_switching
        check_switching(state,points,drag,motion,button,wait,edit)
        motion({"x":20,"y":20})
        hover_mode(0)
        orbit_speeds(90,0)
        wait(lambda:points()["__hover"]["orbitalRunning"])
        initial=points()["__hover"]
        wait(lambda:points()["__hover"]["orbitalPhase"]!=initial["orbitalPhase"])
        moving=points()["__hover"]
        assert moving["items"]!=initial["items"]
        assert all(abs(a-b)<.01 for a,b in zip(initial["glyphAngles"],moving["glyphAngles"]))
        for base,hover in ((180,30),(30,180),(-180,-30),(180,-180),(-180,180)):
            orbit_speeds(base,hover)
            wait(lambda:abs(points()["__hover"]["orbitalVelocity"]-base)<1)
            motion(points()[points()["__hover"]["desktop"]])
            wait(lambda:min(base,hover)<points()["__hover"]["orbitalVelocity"]<max(base,hover))
            wait(lambda:abs(points()["__hover"]["orbitalVelocity"]-hover)<1)
            motion({"x":20,"y":20})
            wait(lambda:min(base,hover)<points()["__hover"]["orbitalVelocity"]<max(base,hover))
            wait(lambda:abs(points()["__hover"]["orbitalVelocity"]-base)<1)
        orbit_speeds(0,180)
        wait(lambda:not points()["__hover"]["orbitalRunning"])
        phase=points()["__hover"]["orbitalPhase"]
        time.sleep(.3)
        assert points()["__hover"]["orbitalPhase"]==phase
        motion(points()[points()["__hover"]["desktop"]])
        wait(lambda:points()["__hover"]["orbitalRunning"])
        motion({"x":20,"y":20})
        wait(lambda:not points()["__hover"]["orbitalRunning"])
        orbit_speeds(0,0)
        print("Plasma: continuous and hover-only orbit, smooth speed changes, upright glyphs and idle cleanup passed")
        print("Native mouse drag: create, add, hover rotation, card reveal, open, reorder and extract passed")
        output.seek(0, 2)
        output.write("NATIVE_INTERACTION_PASSED\n")
        output.flush()
    finally:
        x11.XCloseDisplay(display)

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check regrouping and single-click folder switches through real pointer input."""

import time


def check_switching(state, points, drag, motion, button, wait, edit):
    def click(desktop):
        motion(points()[desktop])
        button(1)
        time.sleep(.08)
        button(0)

    group=next(iter(state()["groups"].values()))
    launcher=group["id"]+".desktop"
    time.sleep(.4)
    wait(lambda: not points().get("__popup",{}).get("visible") or
         points()["__popup"]["live"] and not points()["__popup"]["closing"])
    if not points().get("__popup",{}).get("visible"):
        click(launcher)
    wait(lambda: "test.files.desktop" in points())
    wait(lambda: points().get("__popup",{}).get("live") and
         not points()["__popup"]["closing"])
    time.sleep(.4)
    dock=points()["__dock"]
    drag(points()["test.files.desktop"], {"x":dock["x"]+dock["width"]-10,"y":dock["y"]+dock["height"]/2})
    wait(lambda: not state()["groups"])
    wait(lambda: not points().get("__popup",{}).get("visible") and "test.terminal.desktop" in points())
    time.sleep(.3)
    drag(points()["test.terminal.desktop"],points()["test.files.desktop"])
    wait(lambda: len(state()["groups"])==1)
    first_key=next(iter(state()["groups"]))
    first=state()["groups"][first_key]["id"]+".desktop"
    wait(lambda: first in points())
    edit({"operation":"pin","desktop":"test.four.desktop"})
    wait(lambda: "test.four.desktop" in points())
    time.sleep(.3)
    drag(points()["test.calculator.desktop"],points()["test.four.desktop"])
    wait(lambda: len(state()["groups"])==2)
    second_key=next(key for key in state()["groups"] if key!=first_key)
    second=state()["groups"][second_key]["id"]+".desktop"
    wait(lambda: first in points() and second in points())
    time.sleep(.3)
    for key in (first_key,second_key,first_key,second_key):
        desktop=state()["groups"][key]["id"]+".desktop"
        wait(lambda: desktop in points())
        click(desktop)
        wait(lambda: points().get("__popup",{}).get("key")==key and
             points()["__popup"]["live"] and not points()["__popup"]["closing"])
        time.sleep(.3)
        assert points()["__popup"]["visible"] and points()["__popup"]["key"]==key
    click(desktop)
    wait(lambda: not points()["__popup"]["visible"])
    print("Plasma: native regrouping and one-click folder switching passed")

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check hover controls against the real GTK drawing adapter."""

import json


def check_hover(controller, key, wait, settle):
    from gi.repository import Gdk, Gio
    Gdk.Display.get_default().get_default_seat().get_pointer().warp(Gdk.Screen.get_default(), 10, 10)
    settings = controller.state.settings
    desktop = controller.state.groups[key]["id"] + ".desktop"

    def icon():
        return controller.buttons[desktop].get_child().get_children()[0]

    settings.set_int("hover-angle", 60)
    settings.set_int("hover-speed", 150)
    settings.set_string("hover-effect", "cards")
    settle()
    plain = icon()
    resting = plain.layout
    plain.hover(True)
    settle(.2)
    assert plain.progress == 0 and plain.layout == resting
    assert plain.layout["cardOpacity"] == 0
    settings.set_string("hover-effect", "rotate")
    settle()
    rotating = icon()
    baseline = rotating.layout
    rotating.hover(True)
    wait(lambda: rotating.progress == 1)
    assert rotating.layout["size"] == baseline["size"]
    for before, after in zip(baseline["items"], rotating.layout["items"]):
        assert abs(after["rotation"] - before["rotation"] - 60) < .01
        assert abs(after["rotation"]+after["glyphRotation"]-before["rotation"]-before["glyphRotation"]) < .01
    rotating.hover(False)
    wait(lambda: rotating.progress == 0)
    assert rotating.layout == baseline
    settings.set_int("hover-speed", -999)
    settle()
    reverse = icon()
    baseline = reverse.layout
    reverse.hover(True)
    wait(lambda: reverse.progress == 1)
    for before, after in zip(baseline["items"], reverse.layout["items"]):
        assert abs(after["rotation"] - before["rotation"] + 60) < .01
    reverse.hover(False)
    wait(lambda: reverse.progress == 0)
    settings.set_int("hover-speed", 0)
    settle()
    stationary = icon()
    stationary.hover(True)
    assert stationary.progress == 1 and not stationary.hover_timer
    stationary.hover(False)
    assert stationary.progress == 0 and not stationary.hover_timer
    settings.set_int("hover-speed", 10)
    settle()
    hidden = icon()
    hidden.hover(True)
    assert hidden.hover_timer
    hidden.hide()
    assert not hidden.hover_timer and not hidden.orbit_timer
    hidden.show()
    settings.set_int("hover-speed", 150)
    groups = controller.state.groups.copy()
    groups[key]["alwaysStack"] = True
    settings.set_string("groups", json.dumps(groups))
    settings.set_string("hover-effect", "rotate-cards")
    settle()
    cards = icon()
    assert cards.layout["stacked"]
    compact = cards.layout["width"]
    cards.hover(True)
    wait(lambda: cards.progress == 1)
    assert cards.layout["cardOpacity"] == 1 and cards.layout["items"][0]["rotation"] == 42
    assert compact < cards.layout["width"] <= cards.body*2
    cards.hover(False)
    wait(lambda: cards.progress == 0)
    saved = json.loads(json.dumps(groups))
    members = {entry["desktop"] for entry in groups[key]["apps"]}
    extra = [app for app in Gio.AppInfo.get_all() if app.get_id() and app.get_id().endswith(".desktop")
             and app.get_id() not in members and not app.get_id().startswith("local.groups.")][:3]
    assert len(extra) == 3
    groups[key]["apps"] += [{"desktop":app.get_id(),"label":app.get_name()} for app in extra]
    settings.set_string("groups",json.dumps(groups))
    settle()
    fan = icon()
    assert len(fan.layout["items"]) == 5
    fan.hover(True)
    wait(lambda: fan.progress == 1)
    assert len(fan.layout["items"]) == len(groups[key]["apps"])
    assert fan.layout["width"] <= fan.body*2
    fan.hover(False)
    wait(lambda: fan.progress == 0)
    assert len(fan.layout["items"]) == 5
    groups = saved
    groups[key]["alwaysStack"] = False
    settings.set_string("groups", json.dumps(groups))
    settings.set_string("hover-effect", "none")
    settle()
    settings.set_int("orbit-speed",90)
    settle()
    moving=icon()
    wait(lambda:moving.orbit_angle>0)
    phase=moving.orbit_angle
    faces=[item["rotation"]+item["glyphRotation"] for item in moving.layout["items"]]
    settle(.15)
    assert moving.orbit_angle!=phase and moving.orbit_timer
    assert all(abs(item["rotation"]+item["glyphRotation"]-face)<.001 for item,face in zip(moving.layout["items"],faces))
    for base,hover in ((180,30),(30,180),(-180,-30),(-30,-180),(180,-180),(-180,180)):
        settings.set_int("orbit-speed",base)
        settings.set_int("hover-orbit-speed",hover)
        settle()
        moving=icon()
        moving.hover(False)
        wait(lambda:abs(moving.orbit_velocity-base)<1)
        previous=moving.orbit_velocity
        moving.hover(True)
        assert moving.orbit_velocity==previous
        wait(lambda:min(base,hover)<moving.orbit_velocity<max(base,hover))
        wait(lambda:abs(moving.orbit_velocity-hover)<1)
        entered=moving.orbit_velocity
        moving.hover(False)
        assert moving.orbit_velocity==entered
        wait(lambda:abs(moving.orbit_velocity-base)<1)
    settings.set_int("orbit-speed",0)
    settings.set_int("hover-orbit-speed",180)
    settle()
    moving=icon()
    wait(lambda:not moving.orbit_timer)
    phase=moving.orbit_angle
    moving.hover(True)
    wait(lambda:moving.orbit_timer and moving.orbit_angle>phase)
    moving.hover(False)
    phase=moving.orbit_angle
    assert moving.orbit_timer and moving.orbit_velocity>0
    wait(lambda:not moving.orbit_timer)
    assert moving.orbit_angle!=phase
    phase=moving.orbit_angle
    settle(.15)
    assert moving.orbit_angle==phase
    settings.set_int("hover-orbit-speed",0)
    settle()

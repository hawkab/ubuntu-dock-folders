# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check installation, unavailable launchers, and restoration in a private panel."""

import json
import time
from pathlib import Path

import plasma_manage as manager


def wait(predicate, message, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.1)
    raise RuntimeError(message() if callable(message) else message)


def run(connection, settings, apps):
    from gi.repository import Gio, GLib

    def state():
        value = connection.call_sync(manager.BUS, "/io/github/hawkab/DockFolders",
            "org.freedesktop.DBus.Properties", "Get", GLib.Variant("(ss)", (manager.BUS, "State")),
            None, Gio.DBusCallFlags.NONE, 3000, None)
        return json.loads(value.unpack()[0])

    before = None
    def panel_ready():
        nonlocal before
        try:
            before = next((panel for panel in manager.snapshot() if any(
                widget["type"] == "org.kde.plasma.icontasks" for widget in panel["widgets"])), None)
        except GLib.Error:
            return False
        if before is None:
            return False
        order = before["order"].split(";")
        return all(str(widget["id"]) in order for widget in before["widgets"])
    wait(panel_ready, "The native task-manager panel did not initialize", timeout=10)
    original = next(widget for widget in before["widgets"] if widget["type"] == "org.kde.plasma.icontasks")
    manager.install()
    record = json.loads(manager.STATE.read_text())
    expected = [str(record["widget"]) if item == str(original["id"]) else item for item in before["order"].split(";")]
    wait(lambda: manager.snapshot()[0]["order"].split(";") == expected,
         lambda: f"Installation moved another panel widget: expected {expected}, actual {manager.snapshot()[0]['order']}")
    installed = manager.snapshot()[0]
    assert installed["order"].split(";") == expected, "Installation moved another panel widget"
    assert installed["height"] == before["height"], "Installation changed panel height"
    current = settings.get_string("groups")
    manager.disable()
    def types(panel):
        by_id = {str(widget["id"]): widget["type"] for widget in panel["widgets"]}
        return [by_id[item] for item in panel["order"].split(";") if item]
    wait(lambda: types(manager.snapshot()[0]) == types(before), "Uninstall changed panel widget order")
    restored = manager.snapshot()[0]
    assert types(restored) == types(before), "Uninstall changed panel widget order"
    assert restored["height"] == before["height"]
    assert settings.get_string("groups") == current, "Uninstall removed saved groups"
    manager.install()
    (Path(apps) / "test.calculator.desktop").unlink()
    wait(lambda: len(state()["groups"]["test"]["apps"]) == 2, "Deleted app survived catalog reconciliation")
    for name in ("terminal", "files"):
        (Path(apps) / f"test.{name}.desktop").unlink()
    wait(lambda: not state()["groups"], "An empty group survived deletion of its launchers")
    assert not state()["favorites"] and not state()["undo"]
    time.sleep(.5)
    manager.disable()
    assert not manager.STATE.exists()
    print("NATIVE_LIFECYCLE_PASSED: install, remove, reinstall and live launcher deletion")

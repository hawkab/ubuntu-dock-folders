# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Remove owned Plasma widgets and restore a task manager when its record is valid."""

import json
import os
from pathlib import Path

from plasma_recovery import read_record, recover


def disable(manager):
    """Remove all owned panel slots, including widgets added without the installer."""
    if os.geteuid() == 0:
        raise RuntimeError("Run this command as your desktop user, without sudo.")
    try:
        connection = manager.Gio.bus_get_sync(manager.Gio.BusType.SESSION, None)
        active = connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "NameHasOwner", manager.GLib.Variant("(s)", ("org.kde.plasmashell",)),
            None, manager.Gio.DBusCallFlags.NONE, 1000, None,
        ).unpack()[0]
    except manager.GLib.Error:
        active = False
    if not active:
        recover(Path(manager.GLib.get_user_config_dir()) / "plasma-org.kde.plasma.desktop-appletsrc",
                manager.STATE)
        return
    record = read_record(manager.STATE)
    panels = manager.snapshot()
    panel = next((item for item in panels if item["id"] == record.get("panel")), None)
    managed = next((widget for widget in panel["widgets"]
                    if widget["id"] == record.get("widget") and widget["type"] == manager.ID), None) if panel else None
    original = record.get("original")
    if managed and original:
        script = f"var p=panelById({panel['id']});var w=p.addWidget({json.dumps(original['type'])});"
        for group in original["configuration"]:
            script += "w.currentConfigGroup=" + json.dumps(group["path"]) + ";"
            for key, value in group["values"].items():
                script += "w.writeConfig(" + json.dumps(key) + "," + json.dumps(value) + ");"
        script += "w.reloadConfig();print(w.id);"
        restored = int(manager.evaluate(script))
        manager.place_widget(panel["id"], restored, managed["id"], via=managed["id"])
    for panel in panels:
        owned = [widget for widget in panel["widgets"] if widget["type"] == manager.ID]
        for widget in owned:
            manager.evaluate(f"var p=panelById({panel['id']});var w=p.widgetById({widget['id']});if(w)w.remove();")
        if managed and panel["id"] == record["panel"] and panel["height"] == record.get("managedHeight"):
            manager.evaluate(f"panelById({panel['id']}).height={int(record['height'])};")
    manager.STATE.unlink(missing_ok=True)


def remove_locales(installed, data):
    """Unlink matching catalogs without touching other applications or mapped files."""
    root = installed / "contents/locale"
    for source in root.rglob("*.mo"):
        target = data / "locale" / source.relative_to(root)
        if target.is_file() and target.read_bytes() == source.read_bytes():
            target.unlink()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Activate the Xfce panel plugin and restore only the tasklist it replaced."""

import json
import argparse
import os
from xml.etree import ElementTree as ET
from pathlib import Path

from gi.repository import Gio, GLib
from backup import DATA, backup, read_settings

STATE = DATA / "xfce-panel.json"
BUS = "org.xfce.Xfconf"
PATH = "/org/xfce/Xfconf"
PANEL_BUS = "org.xfce.Panel"


def panel_running():
    return Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
        GLib.Variant("(s)", (PANEL_BUS,)), None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]


def restart_panel():
    """Restart a running panel through D-Bus; return False when it is absent."""
    if not panel_running():
        return False
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            PANEL_BUS, "/org/xfce/Panel", PANEL_BUS, "Terminate", GLib.Variant("(b)", (True,)),
            None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
    except GLib.Error as error:
        if Gio.DBusError.get_remote_error(error) in (
                "org.freedesktop.DBus.Error.ServiceUnknown", "org.freedesktop.DBus.Error.NameHasNoOwner"):
            return False
        raise
    return True


def call(method, parameters):
    return Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
        BUS, PATH, BUS, method, parameters, None, Gio.DBusCallFlags.NONE, 3000, None)


def properties():
    result = call("GetAllProperties", GLib.Variant("(ss)", ("xfce4-panel", "/"))).get_child_value(0)
    return {result.get_child_value(index).get_child_value(0).get_string():
            result.get_child_value(index).get_child_value(1).get_variant()
            for index in range(result.n_children())}


def set_property(key, value):
    call("SetProperty", GLib.Variant("(ssv)", ("xfce4-panel", key, value)))


def arrays(values):
    return {key: value for key, value in values.items()
            if key.startswith("/panels/panel-") and key.endswith("/plugin-ids")}


def panel_slot(values, panel_id=None):
    """Select a panel and its optional tasklist without changing its layout."""
    panels = arrays(values)
    if panel_id is not None:
        key = f"/panels/panel-{panel_id}/plugin-ids"
        if key not in panels:
            raise RuntimeError(f"Xfce panel {panel_id} was not found.")
        panels = {key: panels[key]}
    if not panels:
        raise RuntimeError("No Xfce panel was found.")
    return next(((key, value, plugin) for key, value in panels.items() for plugin in value.unpack()
                 if values.get(f"/plugins/plugin-{plugin}")
                 and values[f"/plugins/plugin-{plugin}"].unpack() == "tasklist"),
                (*next(iter(panels.items())), None))


def enable(extension, backup_directory=None, panel_id=None):
    values = properties()
    if any(value.unpack() == "dockfolders" for key, value in values.items() if key.startswith("/plugins/plugin-") and key.count("/") == 2):
        print("Dock folders is already enabled in the Xfce panel.")
        return
    if not any((Path(directory) / "xfce4/panel/plugins/dockfolders.desktop").is_file()
               for directory in GLib.get_system_data_dirs()):
        raise RuntimeError("Install the Ubuntu Dock Folders package before enabling its Xfce plugin.")
    key, original, replaced = panel_slot(values, panel_id)
    saved = backup(backup_directory, extension)
    settings = read_settings(extension)
    if not settings.get_boolean("xfce-initialized"):
        schema = Gio.SettingsSchemaSource.get_default().lookup("org.gnome.shell", True)
        favorites = list(Gio.Settings.new_full(schema, None, None).get_strv("favorite-apps")) if schema else []
        from gi.repository import GioUnix

        groups = json.loads(settings.get_string("groups"))
        available = {group["id"] + ".desktop" for group in groups.values()}
        favorites = [desktop for desktop in favorites if desktop in available or GioUnix.DesktopAppInfo.new(desktop)]
        for group in groups.values():
            desktop = group["id"] + ".desktop"
            if desktop not in favorites:
                favorites.append(desktop)
        settings.set_strv("xfce-favorites", favorites)
        settings.set_boolean("xfce-initialized", True)
        Gio.Settings.sync()
    ids = {int(key.split("/")[2].removeprefix("plugin-")) for key in values
           if key.startswith("/plugins/plugin-")}
    plugin = max(ids, default=0) + 1
    record = {"plugin": plugin, "replaced": replaced, "panel": key,
              "original": original.print_(True), "backup": str(saved)}
    DATA.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(STATE)
    wanted = [plugin if item == replaced else item for item in original.unpack()]
    if replaced is None:
        wanted.append(plugin)
    set_property(f"/plugins/plugin-{plugin}", GLib.Variant("s", "dockfolders"))
    set_property(key, GLib.Variant("av", [GLib.Variant("i", item) for item in wanted]))
    restart_panel()
    print(f"Enabled Dock folders in Xfce. Backup: {saved}")


def removal_record():
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text())
    except (ValueError, OSError):
        return {}


def disable(restart=True):
    """Remove owned plugins and restore the managed tasklist without replacing other slots."""
    record = removal_record()
    values = properties()
    owned = {int(key.removeprefix("/plugins/plugin-")) for key, value in values.items()
             if key.startswith("/plugins/plugin-") and key.count("/") == 2
             and value.unpack() == "dockfolders"}
    used = {item for value in arrays(values).values() for item in value.unpack()} - owned
    replaced = record.get("replaced")
    original = values.get(f"/plugins/plugin-{replaced}")
    can_restore = original is not None and original.unpack() == "tasklist"
    for key, value in arrays(values).items():
        items = value.unpack()
        if not owned.intersection(items):
            continue
        restored = []
        for item in items:
            if item not in owned:
                restored.append(item)
            elif item == record.get("plugin") and can_restore and replaced not in used:
                restored.append(replaced)
                used.add(replaced)
        set_property(key, GLib.Variant("av", [GLib.Variant("i", item) for item in restored]))
    for plugin in owned:
        call("ResetProperty", GLib.Variant("(ssb)", ("xfce4-panel", f"/plugins/plugin-{plugin}", True)))
    STATE.unlink(missing_ok=True)
    if restart and owned:
        restart_panel()
    print("Removed Dock folders from the Xfce panel. Folder settings were retained.")


def disable_offline():
    """Remove owned slots from the saved Xfconf file when Xfce is not running."""
    record = removal_record()
    file = Path(GLib.get_user_config_dir()) / "xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
    if file.exists():
        tree = ET.parse(file)
        root = tree.getroot()
        plugins = root.find("./property[@name='plugins']")
        owned = {int(node.get("name").removeprefix("plugin-")): node
                 for node in plugins if node.get("name", "").startswith("plugin-")
                 and node.get("value") == "dockfolders"} if plugins is not None else {}
        arrays = root.findall("./property[@name='panels']/property/property[@name='plugin-ids']")
        used = {int(value.get("value")) for array in arrays for value in array.findall("value")} - owned.keys()
        replaced = record.get("replaced")
        original = plugins.find(f"./property[@name='plugin-{replaced}']") if plugins is not None else None
        can_restore = original is not None and original.get("value") == "tasklist"
        for array in arrays:
            for value in list(array):
                if value.tag != "value" or int(value.get("value")) not in owned:
                    continue
                if int(value.get("value")) == record.get("plugin") and can_restore and replaced not in used:
                    value.set("value", str(replaced))
                    used.add(replaced)
                else:
                    array.remove(value)
        for node in owned.values():
            plugins.remove(node)
        if owned:
            temporary = file.with_suffix(".tmp")
            tree.write(temporary, encoding="UTF-8", xml_declaration=True)
            temporary.chmod(file.stat().st_mode & 0o777)
            temporary.replace(file)
    STATE.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("enable","disable"))
    parser.add_argument("--panel", type=int, help="Xfce panel ID to use when enabling")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.exit(1,"Run this command as your desktop user, without sudo.\n")
    owner = Gio.bus_get_sync(Gio.BusType.SESSION,None).call_sync(
        "org.freedesktop.DBus","/org/freedesktop/DBus","org.freedesktop.DBus","NameHasOwner",
        GLib.Variant("(s)",(BUS,)),None,Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
    if args.command == "disable":
        disable() if owner else disable_offline()
    elif owner and "xfce" in os.environ.get("XDG_CURRENT_DESKTOP","").lower():
        try:
            enable(Path("/usr/share/ubuntu-dock-folders/xfce/shared"), panel_id=args.panel)
        except RuntimeError as error:
            parser.exit(1, str(error) + "\n")
    else:
        parser.exit(1,"Log into Xfce before enabling its panel plugin.\n")


if __name__ == "__main__":
    main()

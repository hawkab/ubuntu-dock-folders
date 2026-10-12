#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Install the Plasma widget and restore the task manager it replaces."""

import argparse
import json
import os
import shutil
import signal
import subprocess
import time
import sys
import plasma_update
import plasma_removal
import plasma_provider
from pathlib import Path

from gi.repository import Gio, GLib
from backup import backup
from install_context import atomic_copy, quote_exec

ID = "io.github.hawkab.DockFolders"
BUS = ID + ".Plasma"
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(GLib.get_user_data_dir())
STATE = Path(GLib.get_user_state_dir()) / "ubuntu-dock-folders/plasma-panel.json"
SERVICE = DATA / "dbus-1/services" / (BUS + ".service")


def evaluate(script):
    result = Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
        "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript",
        GLib.Variant("(s)", (script,)), None, Gio.DBusCallFlags.NONE, 5000, None)
    return result.unpack()[0].strip()


def snapshot():
    script = """
function capture(w, path) {
    w.currentConfigGroup=path;
    var values={};
    for (var key of w.configKeys) values[key]=w.readConfig(key);
    var result=[{path:path,values:values}];
    var children=Array.from(w.configGroups);
    for (var group of children) result=result.concat(capture(w,path.concat([group])));
    return result;
}
var result=panels().map(p=>{
    p.currentConfigGroup=['General'];
    return {id:p.id,height:p.height,order:p.readConfig('AppletOrder',''),
        widgets:p.widgets().map(w=>({id:w.id,type:w.type,configuration:
            ['org.kde.plasma.icontasks','org.kde.plasma.taskmanager','io.github.hawkab.DockFolders'].includes(w.type)?capture(w,[]):[]}))};
});
print(JSON.stringify(result));
"""
    return json.loads(evaluate(script))


def check():
    if os.geteuid() == 0:
        raise RuntimeError("Run this command as your desktop user, without sudo.")
    if "kde" not in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
        raise RuntimeError("Run this command in KDE Plasma.")
    version = subprocess.check_output(["plasmashell", "--version"], text=True, stderr=subprocess.DEVNULL)
    if not __import__("re").search(r"plasmashell 6\.(?:[6-9]|[1-9][0-9])\.", version):
        raise RuntimeError("This widget requires KDE Plasma 6.6 or newer.")


def install_locales(installed):
    """Install the widget's translations into the user's locale directory."""
    for source in (installed / "contents/locale").rglob("*.mo"):
        target = DATA / "locale" / source.relative_to(installed / "contents/locale")
        if target.is_file() and target.read_bytes() == source.read_bytes():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_copy(source, target)


def package_path():
    return plasma_provider.source(ROOT)


def write_service(package):
    """Route D-Bus activation to the selected widget provider."""
    SERVICE.parent.mkdir(parents=True, exist_ok=True)
    SERVICE.write_text("[D-BUS Service]\nName=" + BUS + "\nExec=/usr/bin/python3 " +
                       quote_exec(package / "contents/code/service.py", field_codes=False) + "\n")
    Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
        "org.freedesktop.DBus", "ReloadConfig", None, None, Gio.DBusCallFlags.NONE, 3000, None)


def install():
    check()
    package = package_path()
    saved = backup()
    for name in ("plasma-org.kde.plasma.desktop-appletsrc", "plasmashellrc", "kdeglobals"):
        source = Path(GLib.get_user_config_dir()) / name
        if source.exists():
            shutil.copy2(source, saved / name)
            (saved / name).chmod(0o600)
    panels = snapshot()
    existing = next(((panel, widget) for panel in panels for widget in panel["widgets"] if widget["type"] == ID), None)
    if existing:
        raise RuntimeError("The widget is already enabled. Disable it before installing another review build.")
    installed = DATA / "plasma/plasmoids" / ID
    stop_helper()
    provider = plasma_provider.install(package, installed, saved, DATA,
                                       plasma_provider.owned_override(STATE, SERVICE, installed))
    if provider != plasma_provider.SYSTEM_PACKAGE:
        install_locales(provider)
    write_service(provider)
    schema = Gio.SettingsSchemaSource.get_default().lookup("org.gnome.shell", True)
    favorites = list(Gio.Settings.new_full(schema, None, None).get_strv("favorite-apps")) if schema else []
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    connection.call_sync(BUS, "/io/github/hawkab/DockFolders", BUS, "Import",
                         GLib.Variant("(s)", (json.dumps(favorites),)), None, Gio.DBusCallFlags.NONE, 5000, None)
    choice = next(((panel, widget) for panel in panels for widget in panel["widgets"]
                   if widget["type"] in {"org.kde.plasma.icontasks", "org.kde.plasma.taskmanager"}), None)
    if choice:
        panel, original = choice
    elif panels:
        panel, original = panels[0], None
    else:
        raise RuntimeError("No Plasma panel was found.")
    record = {"backup": str(saved), "panel": panel["id"], "height": panel["height"], "managedHeight": panel["height"],
              "original": original, "order": panel["order"], "widget": None}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    STATE.chmod(0o600)
    script = f"var p=panelById({panel['id']});var w=p.addWidget({json.dumps(ID)});print(w.id);"
    widget = int(evaluate(script))
    record["widget"] = widget
    STATE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    order = [int(item) for item in panel["order"].split(";") if item]
    position = order.index(original["id"]) if original and original["id"] in order else len(order)
    neighbour = order[position + 1] if position + 1 < len(order) else 0
    try:
        place_widget(panel["id"], widget, original["id"] if original else neighbour)
    except (RuntimeError, GLib.Error):
        evaluate(f"var w=panelById({panel['id']}).widgetById({widget});if(w)w.remove();")
        STATE.unlink()
        raise
    if original:
        evaluate(f"var old=panelById({panel['id']}).widgetById({original['id']});if(old)old.remove();")
    print(f"Enabled Dock folders in Plasma. Backup: {saved}")


def place_widget(panel, widget, before, via=None):
    """Ask the containment to reorder one widget; verify the resulting order."""
    via = widget if via is None else via
    script = f"var w=panelById({panel}).widgetById({via});w.currentConfigGroup=['General'];"
    script += f"w.writeConfig('placementWidget',{widget});w.writeConfig('placementBefore',{before});w.reloadConfig();"
    evaluate(script)
    for _ in range(20):
        current = next(item for item in snapshot() if item["id"] == panel)
        order = [int(item) for item in current["order"].split(";") if item]
        if widget in order and (not before or before not in order or order.index(widget) + 1 == order.index(before)):
            return
        time.sleep(.1)
    raise RuntimeError("Plasma did not apply the widget position. The panel was retained for recovery.")


def disable():
    plasma_removal.disable(sys.modules[__name__])
    print("Removed Dock folders from Plasma. Folder settings were retained.")


def stop_helper():
    """Stop this widget's helper, including review versions without Shutdown."""
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(BUS, "/io/github/hawkab/DockFolders", BUS,
            "Shutdown", None, None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
    except GLib.Error:
        try:
            value = Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus", "GetConnectionUnixProcessID", GLib.Variant("(s)", (BUS,)),
                None, Gio.DBusCallFlags.NONE, 1000, None)
            process = Path("/proc") / str(value.unpack()[0])
            command = (process / "cmdline").read_bytes().split(b"\0")
            script = DATA / "plasma/plasmoids" / ID / "contents/code/service.py"
            if process.stat().st_uid == os.getuid() and str(script).encode() in command:
                os.kill(int(process.name), signal.SIGTERM)
        except (GLib.Error, OSError):
            pass


def uninstall():
    """Restore the panel, stop the helper, and remove the owned user widget."""
    disable()
    stop_helper()
    SERVICE.unlink(missing_ok=True)
    installed = DATA / "plasma/plasmoids" / ID
    plasma_removal.remove_locales(installed, DATA)
    if installed.exists():
        shutil.rmtree(installed)


def update():
    """Replace only this widget while preserving panel and appearance settings."""
    check()
    record = json.loads(STATE.read_text())
    panel = next(item for item in snapshot() if item["id"] == record["panel"])
    own = next(widget for widget in panel["widgets"] if widget["id"] == record["widget"])
    saved = backup()
    shutil.copy2(STATE, saved / "plasma-panel.json")
    for name in ("plasma-org.kde.plasma.desktop-appletsrc", "plasmashellrc"):
        shutil.copy2(Path(GLib.get_user_config_dir()) / name, saved / name)
    if plasma_update.managed_shell():
        plasma_update.refresh(sys.modules[__name__], saved, panel, DATA / "plasma/plasmoids" / ID)
        print(f"Updated Dock folders. Backup: {saved}")
        return
    if package_path() == plasma_provider.SYSTEM_PACKAGE:
        raise RuntimeError("Updating a system widget requires a systemd-managed Plasma session. "
                           "The current widget and backup were retained.")
    subprocess.run(["kpackagetool6", "--type", "Plasma/Applet", "--upgrade", str(package_path())], check=True)
    install_locales(DATA / "plasma/plasmoids" / ID)
    stop_helper()
    script = f"var p=panelById({panel['id']});var w=p.addWidget({json.dumps(ID)});"
    for group in own["configuration"]:
        script += "w.currentConfigGroup=" + json.dumps(group["path"]) + ";"
        for key, value in group["values"].items():
            if not key.startswith("placement"):
                script += "w.writeConfig(" + json.dumps(key) + "," + json.dumps(value) + ");"
    script += "w.reloadConfig();print(w.id);"
    widget = int(evaluate(script))
    original_order = [int(item) for item in record["order"].split(";") if item]
    original = record["original"]
    position = original_order.index(original["id"]) if original and original["id"] in original_order else len(original_order)
    neighbour = original_order[position + 1] if position + 1 < len(original_order) else 0
    try:
        place_widget(panel["id"], widget, neighbour)
    except (RuntimeError, GLib.Error):
        evaluate(f"var w=panelById({panel['id']}).widgetById({widget});if(w)w.remove();")
        raise
    evaluate(f"var w=panelById({panel['id']}).widgetById({own['id']});if(w)w.remove();")
    record["widget"] = widget
    if panel["height"] == record["managedHeight"]:
        evaluate(f"panelById({panel['id']}).height={record['height']};")
    record["managedHeight"] = record["height"]
    STATE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(f"Updated Dock folders. Backup: {saved}")


def preferences():
    evaluate("for(var p of panels()){for(var w of p.widgets()){if(w.type===" + json.dumps(ID) + "){w.showConfigurationInterface();}}}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("install", "disable", "preferences", "update", "uninstall"))
    args = parser.parse_args()
    try:
        {"install": install, "disable": disable, "preferences": preferences, "update": update, "uninstall": uninstall}[args.command]()
    except (RuntimeError, ValueError, subprocess.CalledProcessError, GLib.Error) as error:
        parser.exit(1, str(error) + "\n")

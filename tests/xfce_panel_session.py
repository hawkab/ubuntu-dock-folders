# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check installed plugin embedding, app removal and tasklist restoration."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from gi.repository import Gio, GLib
from PIL import Image, ImageGrab
from xfce_native_pointer import COLORS, check_installed
from xfce_plugin_fixture import install_source_plugin

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(os.environ["DOCK_FOLDERS_TEST_XFCE_SOURCE"]) if os.environ.get("DOCK_FOLDERS_TEST_XFCE_SOURCE") else None
SHARED = SOURCE / "shared" if SOURCE else Path("/usr/share/ubuntu-dock-folders/xfce/shared")
sys.path.insert(0, str(ROOT / "scripts" if SOURCE else Path("/usr/share/ubuntu-dock-folders/xfce-management")))
import xfce_manage
sys.path.insert(0, str(SHARED / "adapters"))
from runtime import CoreRuntime
sys.path.insert(0, str(ROOT / "scripts"))
from session_runner import processes, MARKER


def wait_for(check, message, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        result = check()
        if result:
            return result
        time.sleep(.1)
    raise AssertionError(message)


def controllers():
    found = []
    for pid in processes(os.environ[MARKER]):
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            backend = SOURCE / "panel.py" if SOURCE else Path("/usr/share/ubuntu-dock-folders/xfce/panel.py")
            if str(backend).encode() in args:
                found.append(pid)
        except OSError:
            pass
    return found


def main():
    home = Path(os.environ["HOME"])
    if SOURCE:
        install_source_plugin(home, SOURCE)
    apps = Path(os.environ["XDG_DATA_HOME"]) / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    for name, color in COLORS.items():
        icon = home / (name + ".png")
        Image.new("RGB", (64, 64), color).save(icon)
        (apps / f"test.{name}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name.title()}\nIcon={icon}\nExec=/usr/bin/true\n")
    config = Path(os.environ["XDG_CONFIG_HOME"]) / "xfce4/xfconf/xfce-perchannel-xml"
    config.mkdir(parents=True)
    (config / "xfce4-panel.xml").write_text('''<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-panel" version="1.0">
  <property name="configver" type="int" value="2"/>
  <property name="panels" type="array"><value type="int" value="1"/>
    <property name="panel-1" type="empty">
      <property name="position" type="string" value="p=10;x=550;y=728"/>
      <property name="position-locked" type="bool" value="true"/>
      <property name="size" type="uint" value="64"/>
      <property name="length" type="uint" value="100"/>
      <property name="plugin-ids" type="array"><value type="int" value="1"/><value type="int" value="2"/><value type="int" value="3"/></property>
    </property>
  </property>
  <property name="plugins" type="empty">
    <property name="plugin-1" type="string" value="applicationsmenu"/>
    <property name="plugin-2" type="string" value="tasklist"/>
    <property name="plugin-3" type="string" value="clock"/>
  </property>
</channel>''')
    settings = xfce_manage.read_settings(SHARED)
    assert (settings.get_int("group-icon-size"), settings.get_int("mini-icon-size"),
            settings.get_int("animation-speed"), settings.get_string("animation")) == (120, 230, 180, "flow")
    core = CoreRuntime(SHARED)
    entries = {f"test.{name}.desktop": {"desktop": f"test.{name}.desktop", "label": name.title()}
               for name in ("terminal", "files")}
    created = core.call("transaction", {"state": {"groups": {}, "favorites": list(entries)},
        "command": {"operation": "create", "desktop": "test.terminal.desktop", "target": "test.files.desktop", "name": "Tools"},
        "entries": entries, "token": "native"})["state"]
    assert not created["groups"]["folder-native"]["showLabel"]
    core.close()
    settings.set_string("groups", json.dumps(created["groups"]))
    settings.set_strv("xfce-favorites", created["favorites"])
    settings.set_boolean("xfce-initialized", True)
    Gio.Settings.sync()
    wm = subprocess.Popen(["xfwm4", "--replace", "--compositor=on"])
    with (home / "panel.log").open("w+") as log:
        panel = subprocess.Popen(["xfce4-panel", "--disable-wm-check"], stdout=log, stderr=log)
        try:
            def available():
                try:
                    return bool(xfce_manage.properties())
                except GLib.Error:
                    return False
            wait_for(available, "Xfconf did not start")
            wait_for(xfce_manage.panel_running, "Xfce panel did not register its D-Bus service")
            if SOURCE:
                xfce_manage.enable(SHARED)
            else:
                subprocess.run(["/usr/bin/ubuntu-dock-folders-xfce", "enable"], check=True, timeout=15)
            time.sleep(1)
            ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(ROOT.parent / "parity-xfce-native-startup.png")
            pid = wait_for(controllers, "Installed plugin did not embed its Python controller")
            values = xfce_manage.properties()
            plugin = json.loads(xfce_manage.STATE.read_text())["plugin"]
            assert values["/panels/panel-1/plugin-ids"].unpack() == [1, plugin, 3]
            assert values["/plugins/plugin-3"].unpack() == "clock"
            time.sleep(1)
            ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(ROOT.parent / "parity-xfce-native-panel.png")
            check_installed(settings, wait_for)
            (apps / "test.files.desktop").unlink()
            wait_for(lambda: settings.get_string("groups") == "{}" and
                     settings.get_strv("xfce-favorites") == ["test.terminal.desktop"],
                     "Removed app was not reconciled in groups and favorites")
            before = settings.get_string("groups")
            def cpu_ticks():
                values = Path(f"/proc/{pid[0]}/stat").read_text().split(")", 1)[1].split()
                return int(values[11]) + int(values[12])
            ticks = cpu_ticks()
            time.sleep(1)
            assert controllers() == pid and settings.get_string("groups") == before, "Plugin restarted or rewrote state repeatedly"
            assert cpu_ticks() - ticks < os.sysconf("SC_CLK_TCK") / 5, "Missing app caused an idle CPU loop"
            if SOURCE:
                xfce_manage.disable()
            else:
                subprocess.run(["/usr/bin/ubuntu-dock-folders-xfce", "disable"], check=True, timeout=15)
            wait_for(lambda: not controllers(), "Controller survived removal")
            values = xfce_manage.properties()
            assert values["/panels/panel-1/plugin-ids"].unpack() == [1, 2, 3]
            assert values["/plugins/plugin-2"].unpack() == "tasklist"
            assert values["/plugins/plugin-3"].unpack() == "clock"
            assert settings.get_string("groups") == before and not xfce_manage.STATE.exists()
            ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(ROOT.parent / "parity-xfce-native-restored.png")
            errors = (home / "panel.log").read_text()
            assert not any(word in errors for word in ("Traceback", "CRITICAL", "failed to load")), errors
            print("Native Xfce: installed socket, clean defaults, removed app, stable worker, tasklist restoration passed")
        finally:
            print((home / "panel.log").read_text(), end="", flush=True)
            subprocess.run(["xfce4-panel", "--quit"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if panel.poll() is None:
                panel.terminate()
            panel.wait(timeout=3)
            wm.terminate()
            wm.wait(timeout=3)


if __name__ == "__main__":
    main()

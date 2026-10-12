# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise native Wayland panel widgets and preserve valid saved groups."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, Gtk
from xfce_plugin_fixture import install_source_plugin
from PIL import Image
from xfce_native_pointer import COLORS, check_installed
from wayland_pointer import Pointer
from xfce_wayland_checks import check as check_wayland
from gi.repository import GLib

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(os.environ["DOCK_FOLDERS_TEST_XFCE_SOURCE"]) if os.environ.get("DOCK_FOLDERS_TEST_XFCE_SOURCE") else None
sys.path.insert(0, str(ROOT / "scripts"))
from backup import read_settings
from session_runner import processes, MARKER


def main():
    assert Gdk.Display.get_default().__gtype__.name == "GdkWaylandDisplay"
    assert os.environ["XDG_SESSION_TYPE"] == "wayland"
    home = Path(os.environ["HOME"])
    library = install_source_plugin(home, SOURCE) if SOURCE else Path("/usr/lib") / subprocess.check_output(
        ["dpkg-architecture", "-qDEB_HOST_MULTIARCH"], text=True).strip() / "xfce4/panel/plugins/libdockfolders.so"
    shared = SOURCE / "shared" if SOURCE else Path("/usr/share/ubuntu-dock-folders/xfce/shared")
    settings = read_settings(shared)
    apps = Path(os.environ["XDG_DATA_HOME"]) / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    colors = COLORS
    for name, color in colors.items():
        icon = home / (name + ".png")
        Image.new("RGB", (64,64), color).save(icon)
        (apps / f"test.{name}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name}\nIcon={icon}\nExec=/usr/bin/true\n")
    groups = json.dumps({"saved": {"id": "local.groups.saved", "name": "Saved folder",
        "apps": [{"desktop": "test.terminal.desktop", "label": "Terminal"}, {"desktop": "test.files.desktop", "label": "Files"}]}})
    settings.set_string("groups", groups)
    settings.set_strv("xfce-favorites", ["local.groups.saved.desktop"])
    Gio.Settings.sync()
    config = Path(os.environ["XDG_CONFIG_HOME"]) / "xfce4/xfconf/xfce-perchannel-xml"
    config.mkdir(parents=True)
    (config / "xfce4-panel.xml").write_text('''<channel name="xfce4-panel" version="1.0">
  <property name="configver" type="int" value="2"/>
  <property name="panels" type="array"><value type="int" value="1"/>
    <property name="panel-1" type="empty">
      <property name="position" type="string" value="p=10;x=640;y=690"/>
      <property name="size" type="uint" value="64"/>
      <property name="length" type="uint" value="100"/>
      <property name="plugin-ids" type="array"><value type="int" value="1"/><value type="int" value="2"/></property>
    </property>
  </property>
  <property name="plugins" type="empty">
    <property name="plugin-1" type="string" value="dockfolders"/>
    <property name="plugin-2" type="string" value="clock"/>
  </property>
</channel>''')
    with (home / "panel.log").open("w+") as log:
        panel = subprocess.Popen(["xfce4-panel", "--disable-wm-check"], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                assert panel.poll() is None, (home / "panel.log").read_text()
                if str(library) in Path(f"/proc/{panel.pid}/maps").read_text():
                    break
                time.sleep(.1)
            else:
                raise AssertionError("Wayland panel did not load the native plugin")
            for _ in range(3):
                time.sleep(1)
                assert panel.poll() is None
            assert json.loads(settings.get_string("groups"))["saved"]["name"] == "Saved folder"
            assert settings.get_strv("xfce-favorites") == ["local.groups.saved.desktop"]
            def screenshot():
                file = home / "native-panel.png"
                subprocess.run(["grim",str(file)],check=True,timeout=3)
                image = Image.open(file).convert("RGB")
                image.save(ROOT.parent / "xfce-native-wayland-debug.png")
                return image
            image = screenshot()
            for color in (COLORS["terminal"], COLORS["files"]):
                assert sum(pixel == color for pixel in image.getdata()) > 50, "Native folder icons were not drawn"
            def wait(check, message):
                deadline = time.monotonic()+8
                while time.monotonic() < deadline:
                    while GLib.MainContext.default().pending():
                        GLib.MainContext.default().iteration(False)
                    if check():
                        return
                    assert panel.poll() is None, (home / "panel.log").read_text()
                    time.sleep(.12)
                raise AssertionError(message)
            check_installed(settings, wait, Pointer(image.width,image.height), screenshot)
            check_wayland(settings, panel, wait, screenshot)
            diagnostic = Path(os.environ["XDG_STATE_HOME"])/"ubuntu-dock-folders/xfce.log"
            assert not diagnostic.exists() or "ERROR" not in diagnostic.read_text(), diagnostic.read_text()
            errors = (home / "panel.log").read_text()
            assert not any(word in errors for word in ("GtkSocket", "CRITICAL", "assertion", "Traceback")), errors
            print("Xfce/Wayland: native GTK icons rendered; panel stayed alive; saved groups preserved")
        finally:
            subprocess.run(["xfce4-panel", "--quit"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if panel.poll() is None:
                panel.terminate()
            panel.wait(timeout=5)
            diagnostic = Path(os.environ["XDG_STATE_HOME"])/"ubuntu-dock-folders/xfce.log"
            if diagnostic.exists():
                (ROOT.parent / "xfce-native-errors.log").write_text(diagnostic.read_text())
            (ROOT.parent / "xfce-native-panel.log").write_text((home / "panel.log").read_text())
            print((home / "panel.log").read_text(), end="", flush=True)
    (home / "xfce-wayland.ok").touch()


if __name__ == "__main__":
    main()

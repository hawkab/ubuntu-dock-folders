#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Load the Plasma widget in a separate X11/D-Bus session with temporary settings."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from session_runner import run_isolated, update_activation_environment

ROOT = Path(__file__).resolve().parent.parent
BUS = "io.github.hawkab.DockFolders.Plasma"


def main():
    with tempfile.TemporaryDirectory(prefix="dock-folders-plasma-", ignore_cleanup_errors=True) as directory:
        home = Path(directory)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
                   XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
                   XDG_STATE_HOME=str(home / "state"), GSETTINGS_BACKEND="keyfile",
                   QT_QPA_PLATFORM="xcb", QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="org.kde.desktop",
                   XDG_CURRENT_DESKTOP="KDE", XDG_SESSION_TYPE="x11", WAYLAND_DISPLAY="",
                   LANGUAGE=os.environ.get("DOCK_FOLDERS_TEST_LANGUAGE","en"), LC_ALL="ru_RU.UTF-8" if os.environ.get("DOCK_FOLDERS_TEST_LANGUAGE")=="ru" else "en_US.UTF-8", GIO_USE_VFS="local", NO_AT_BRIDGE="1",
                   GDK_BACKEND="x11", XDG_DATA_DIRS="/usr/local/share:/usr/share")
        if "--settings" in sys.argv and "--shader" in sys.argv:
            env.pop("QT_QUICK_BACKEND",None)
            env["LIBGL_ALWAYS_SOFTWARE"]="1"
        run_isolated(["xvfb-run", "-a", "-s", "-screen 0 1100x760x24",
                        "/usr/bin/python3", str(Path(__file__).resolve()), "--session", *sys.argv[1:]],
                       env)


def session():
    from gi.repository import Gio
    update_activation_environment()

    home = Path(os.environ["HOME"])
    package = home / "package"
    shutil.copytree(ROOT / "build/plasma", package)
    shutil.copytree(package / "contents/locale", Path(os.environ["XDG_DATA_HOME"]) / "locale")
    apps = Path(os.environ["XDG_DATA_HOME"]) / "applications"
    apps.mkdir(parents=True)
    for name, icon in (("terminal", "utilities-terminal"), ("files", "system-file-manager"), ("calculator", "accessories-calculator")):
        (apps / f"test.{name}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name.title()}\nExec=true\nIcon={icon}\n")
    source = Gio.SettingsSchemaSource.new_from_directory(str(package / "contents/schemas"), Gio.SettingsSchemaSource.get_default(), False)
    settings = Gio.Settings.new_full(source.lookup("org.gnome.shell.extensions.dock-groups", False), None, None)
    settings.set_string("groups", json.dumps({"test": {"id": "local.groups.test", "name": "Tools", "icon": "folder",
        "colors": ["#40505c", "#263d4a"], "apps": [{"desktop": f"test.{name}.desktop", "label": name.title()} for name in ("terminal", "files", "calculator")]}}))
    settings.set_strv("plasma-favorites", ["local.groups.test.desktop"])
    settings.set_boolean("plasma-initialized", True)
    Gio.Settings.sync()
    qml = package / "contents/ui/main.qml"
    text = qml.read_text()
    text = text.replace("    Component.onCompleted: {\n        properties.updateAll();", """
    Timer {
        interval: 1800
        running: true
        onTriggered: {
            console.log("PLASMA_READY", Object.keys(root.state.groups).length, root.taskDelegateModel?.count);
            if (Object.keys(root.state.groups).length !== 1) { console.error("PLASMA_STATE_FAILED", "PLASMA_SETTINGS_FAILED"); return; }
            root.currentKey = "test";
            popup.visible = true;
            folderSettings.show();
            root.edit({operation: "move", desktop: "test.calculator.desktop", key: "test", before: "test.terminal.desktop"});
        }
    }
    Timer {
        interval: 3500
        running: true
        onTriggered: {
            console.log("PLASMA_CHECK", root.state.groups.test?.apps[0]?.desktop, root.state.undo);
            root.edit({operation: "undo"});
        }
    }
    Component.onCompleted: {
        properties.updateAll();""")
    if "--apply" in sys.argv:
        from plasma_apply_checks import prepare
        text = prepare(package, settings, apps)
        if "--palette" in sys.argv:
            folder = package / "contents/ui/FolderSettings.qml"
            folder.write_text(folder.read_text().replace("interval: 250; repeat: true", "interval: 1500; repeat: true"))
        Gio.Settings.sync()
    if "--folders" in sys.argv:
        from plasma_folder_checks import prepare
        text=prepare(package,apps,qml.read_text())
        Gio.Settings.sync()
    if "--settings" in sys.argv:
        from plasma_settings_checks import prepare
        text=prepare(package,qml.read_text())
    qml.write_text(text)
    wm = subprocess.Popen(["xfwm4", "--replace", "--compositor=off"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    backend = subprocess.Popen(["/usr/bin/python3", str(package / "contents/code/service.py")],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if "--settings" in sys.argv:
            def capture_settings():
                from PIL import ImageGrab
                time.sleep(2.7)
                ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(ROOT.parent/"plasma-general-settings.png")
                time.sleep(1.1)
                ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(ROOT.parent/"plasma-general-settings-open.png")
            threading.Thread(target=capture_settings,daemon=True).start()
        if "--folders" in sys.argv:
            def capture_folders():
                from PIL import ImageGrab
                time.sleep(6)
                ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(ROOT.parent/"plasma-existing-folders.png")
            threading.Thread(target=capture_folders,daemon=True).start()
        if "--palette" in sys.argv:
            def capture_palette():
                from PIL import ImageGrab
                time.sleep(3.8)
                ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(ROOT.parent / "plasma-palette-initial.png")
                time.sleep(3)
                ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(ROOT.parent / "plasma-palette-reopened.png")
            threading.Thread(target=capture_palette, daemon=True).start()
        duration = "19s" if "--palette" in sys.argv else "12s" if "--folders" in sys.argv or "--settings" in sys.argv else "7s"
        result = subprocess.run(["timeout", duration, "plasmawindowed", str(package)],
                                capture_output=True, text=True, timeout=22)
        output = result.stdout + result.stderr
        print(output)
        passed = "PLASMA_SETTINGS_PASSED" in output if "--settings" in sys.argv else all(marker in output for marker in ("PLASMA_FOLDERS_PASSED","FOLDER_RUNNING_FILTER_PASSED","FOLDER_LIFETIME_PASSED")) if "--folders" in sys.argv else ("PLASMA_BULK_APPLY_PASSED" in output and "PLASMA_PALETTE_PASSED" in output) if "--apply" in sys.argv else (
            "PLASMA_READY 1" in output and "PLASMA_CHECK test.calculator.desktop true" in output)
        if result.returncode not in (0, 124) or not passed:
            raise RuntimeError("Plasma widget did not complete its isolated checks")
        errors = ("ReferenceError", "TypeError", "Cannot assign", "Component is not ready", "Error:", "Binding loop", "PLASMA_STATE_FAILED", "PLASMA_SETTINGS_FAILED")
        if any(error in output for error in errors):
            raise RuntimeError("Plasma widget emitted a QML error")
    finally:
        backend.terminate()
        stdout, stderr = backend.communicate(timeout=3)
        print(stdout + stderr)
        wm.terminate()
        wm.wait(timeout=3)


if __name__ == "__main__":
    session() if "--session" in sys.argv else main()

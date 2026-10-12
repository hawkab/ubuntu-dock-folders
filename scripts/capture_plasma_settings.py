# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Capture the actual Plasma configuration pages in a private widget package."""

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from capture_settings import ROOT, capture_window, center_window, sample_settings


def visible_window():
    tree = subprocess.check_output(["xwininfo", "-root", "-tree"], text=True)
    windows = []
    for line in tree.splitlines():
        match = re.search(r'(0x[0-9a-f]+) "([^"]+)".*?\s(\d+)x(\d+)\+', line)
        if match and any(title in match[2] for title in ("Dock folders", "Folder appearance")):
            windows.append((int(match[3])*int(match[4]), match[1]))
    if not windows:
        raise RuntimeError("The settings window is not visible")
    return max(windows)[1]


def global_pages(package):
    source = package / "contents/ui/ConfigGeneral.qml"
    text = source.read_text().replace("import QtQuick\n", "import QtQuick\nimport QtQuick.Window\n")
    text = text.replace("    property bool ready: false", '''
    property int captureStep: 0
    Timer {
        interval: 1200; running: globalSettings.ready; repeat: true
        onTriggered: {
            const frame = globalSettings.Window.window;
            if (captureStep === 0) {
                frame.width = 820; frame.height = 830;
                tabs.currentIndex = 0;
                cfg_hoverOrbitSpeed = 999;
                cfg_hoverEffect = Core.hoverChoice(true, true).id;
            } else if (captureStep === 1) console.log("DOC_CAPTURE:general-settings.png");
            else if (captureStep === 2) {tabs.currentIndex = 1;frame.height = 660;}
            else if (captureStep === 3) console.log("DOC_CAPTURE:general-settings-open.png");
            else if (captureStep === 4) {tabs.currentIndex = 2;frame.height = 560;}
            else if (captureStep === 5) {console.log("DOC_CAPTURE:existing-folders.png");stop();}
            captureStep++;
        }
    }
    property bool ready: false''')
    source.write_text(text)
    return '''
    Timer {interval: 1200;running: true;onTriggered: Plasmoid.internalAction("configure").trigger()}
'''


def folder_pages(package):
    source = package / "contents/ui/FolderSettings.qml"
    text = source.read_text().replace("    id: window", '''
    id: window
    property int captureStep: 0
    Timer {
        interval: 1200; running: window.visible; repeat: true
        onTriggered: {
            if (captureStep === 0) {window.width = 680;window.height = 600;tabs.currentIndex = 0;}
            else if (captureStep === 1) console.log("DOC_CAPTURE:folder-settings-dock.png");
            else if (captureStep === 2) {tabs.currentIndex = 1;window.height = 720;}
            else if (captureStep === 3) {console.log("DOC_CAPTURE:folder-settings-open.png");stop();}
            captureStep++;
        }
    }''')
    source.write_text(text)
    return '''
    Timer {interval: 1200;running: true;onTriggered: {root.currentKey = "browsers";folderSettings.show();}}
'''


def run_widget(package, timer, expected):
    source = package / "contents/ui/main.qml"
    source.write_text(source.read_text().replace("    Component.onCompleted: {\n        properties.updateAll();",
        timer + "    Component.onCompleted: {\n        properties.updateAll();"))
    process = subprocess.Popen(["plasmawindowed", str(package)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    timeout = threading.Timer(28, process.kill)
    timeout.daemon = True
    timeout.start()
    captured = set()
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            if "DOC_CAPTURE:" in line:
                name = line.split("DOC_CAPTURE:", 1)[1].strip()
                window = visible_window()
                center_window(window)
                time.sleep(.3)
                process.send_signal(signal.SIGSTOP)
                try:
                    capture_window(window, ROOT / "docs/plasma" / name, center=False)
                finally:
                    process.send_signal(signal.SIGCONT)
                captured.add(name)
                if captured == set(expected):
                    break
            elif any(error in line for error in ("ReferenceError", "TypeError", "Cannot assign", "Binding loop")):
                raise RuntimeError(line.strip())
        if captured != set(expected):
            raise RuntimeError(f"Incomplete Plasma captures: {sorted(captured)}")
    finally:
        timeout.cancel()
        process.terminate()
        process.wait(timeout=5)


def session():
    from gi.repository import Gio
    home = Path(os.environ["HOME"])
    config = Path(os.environ["XDG_CONFIG_HOME"])
    config.mkdir(parents=True, exist_ok=True)
    shutil.copy2("/usr/share/color-schemes/BreezeDark.colors", config / "kdeglobals")
    package = home / "package"
    shutil.copytree(ROOT / "build/plasma", package)
    shutil.copytree(package / "contents/locale", Path(os.environ["XDG_DATA_HOME"]) / "locale")
    schema = Gio.SettingsSchemaSource.new_from_directory(str(package / "contents/schemas"),
        Gio.SettingsSchemaSource.get_default(), False).lookup("org.gnome.shell.extensions.dock-groups", False)
    settings = Gio.Settings.new_full(schema, None, None)
    sample_settings(settings, Path(os.environ["XDG_DATA_HOME"]))
    backend = subprocess.Popen(["/usr/bin/python3", str(package / "contents/code/service.py")],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        run_widget(package, global_pages(package),
                   ("general-settings.png", "general-settings-open.png", "existing-folders.png"))
        shutil.rmtree(package)
        shutil.copytree(ROOT / "build/plasma", package)
        run_widget(package, folder_pages(package), ("folder-settings-dock.png", "folder-settings-open.png"))
    finally:
        backend.terminate()
        _, errors = backend.communicate(timeout=5)
        if "Traceback" in errors:
            raise RuntimeError(errors)

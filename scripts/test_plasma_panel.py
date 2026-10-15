#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise a native Plasma panel in an isolated KWin desktop."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from session_runner import run_isolated, update_activation_environment
from plasma_probe import instrument

ROOT = Path(__file__).resolve().parent.parent
ID = "io.github.hawkab.DockFolders"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("wayland", "x11"), default="wayland")
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--software-ui", action="store_true")
    options, remaining = parser.parse_known_args()
    if options.software_ui:
        remaining.append("--ui")
    if options.backend == "x11" and not shutil.which("kwin_x11"):
        raise RuntimeError("Install KWin's X11 backend before running this check.")
    with tempfile.TemporaryDirectory(prefix="dock-folders-kwin-", ignore_cleanup_errors=True) as directory:
        home = Path(directory)
        runtime = home / "runtime"
        runtime.mkdir(mode=0o700)
        if "--glass" in remaining or "--ui" in remaining:
            config = home / "config"
            config.mkdir()
            fixture = "inheritedglstateEnabled=true\n" if "--gl-state" in remaining else ""
            if "--presented" in remaining: fixture += "presentedframeEnabled=true\n"
            renderer = "QPainter" if options.software_ui else "OpenGL"
            (config / "kwinrc").write_text("[Plugins]\nblurEnabled=true\n" + fixture + f"[Compositing]\nBackend={renderer}\nOpenGLIsUnsafe=false\n")
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
                   XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
                   XDG_STATE_HOME=str(home / "state"), XDG_RUNTIME_DIR=str(runtime),
                   XDG_DATA_DIRS="/usr/local/share:/usr/share", GSETTINGS_BACKEND="keyfile",
                   QT_QPA_PLATFORM="xcb", XDG_CURRENT_DESKTOP="KDE", WAYLAND_DISPLAY="",
                   LIBGL_ALWAYS_SOFTWARE="1", QSG_RHI_BACKEND="opengl", GIO_USE_VFS="local",
                   DOCK_FOLDERS_TEST_PLASMA_BACKEND=options.backend,
                   DOCK_FOLDERS_TEST_SOFTWARE_UI="1" if options.software_ui else "0",
                   DOCK_FOLDERS_TEST_PRESENTED="1" if "--presented" in remaining else "0",
                   LANGUAGE="en", LC_ALL="C.UTF-8", QT_LOGGING_RULES="*.debug=false;qml.debug=true")
        env.pop("QT_QUICK_BACKEND", None)
        plugins = str(ROOT / ("build/kwinplugins-" + options.backend))
        env["QT_PLUGIN_PATH"] = plugins + os.pathsep + env.get("QT_PLUGIN_PATH", "")
        if env.get("QT_PLUGIN_PATH"):
            env["QT_PLUGIN_PATH"] = os.pathsep.join(str(Path(path).resolve()) for path in env["QT_PLUGIN_PATH"].split(os.pathsep))
        if options.hardware: env.pop("LIBGL_ALWAYS_SOFTWARE", None)
        if any(mode in remaining for mode in ("--glass", "--ui")) and "--presented" not in remaining:
            env["KWIN_SCREENSHOT_NO_PERMISSION_CHECKS"] = "1"
        run_isolated(["xvfb-run", "-a", "-s", "-screen 0 1100x760x24",
                        "/usr/bin/python3", str(Path(__file__).resolve()), "--compositor", *remaining],
                       env)


def compositor():
    update_activation_environment()
    arguments = ["/usr/bin/python3", str(Path(__file__).resolve()), "--desktop",
                 *[value for value in sys.argv[1:] if value != "--compositor"]]
    if os.environ["DOCK_FOLDERS_TEST_PLASMA_BACKEND"] == "x11":
        log = (Path(os.environ["HOME"]) / "compositor.log").open("w") if "--glass" in sys.argv else None
        wm = subprocess.Popen(["kwin_x11", "--replace", "--no-kactivities"],
                              stdout=log or subprocess.DEVNULL, stderr=log or subprocess.DEVNULL)
        try:
            subprocess.run(arguments, check=True)
        except BaseException:
            if log:
                log.flush()
                print((Path(os.environ["HOME"]) / "compositor.log").read_text()[-18000:])
            raise
        finally:
            wm.terminate()
            wm.wait(timeout=5)
            if log: log.close()
        check_blur_log()
        return
    command = " ".join(shlex.quote(value) for value in arguments)
    compositor_binary = Path(os.environ["HOME"]) / "kwin_wayland"
    shutil.copyfile(shutil.which("kwin_wayland"), compositor_binary)
    compositor_binary.chmod(0o755)
    pipewire = subprocess.Popen(["pipewire"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        virtual = any(mode in sys.argv for mode in ("--glass", "--ui")) and os.environ["DOCK_FOLDERS_TEST_SOFTWARE_UI"] != "1"
        output = ["--virtual"] if virtual else ["--x11-display", os.environ["DISPLAY"]]
        with (Path(os.environ["HOME"]) / "compositor.log").open("w") as log:
            result = subprocess.run([str(compositor_binary), *output, "--width", "1100",
                    "--height", "760", "--no-lockscreen", "--no-global-shortcuts",
                    "--socket", "dock-folders-review", "--exit-with-session", command],
                   stdout=log if "--glass" in sys.argv else None,
                   stderr=log if "--glass" in sys.argv else None)
        if result.returncode:
            if "--glass" in sys.argv: print((Path(os.environ["HOME"]) / "compositor.log").read_text()[-18000:])
            result.check_returncode()
    finally:
        pipewire.terminate()
        pipewire.wait(timeout=3)
    check_blur_log()


def check_blur_log():
    if "--glass" not in sys.argv: return
    log = (Path(os.environ["HOME"]) / "compositor.log").read_text()
    errors = [line for line in log.splitlines() if any(term in line for term in
              ("GL_INVALID_VALUE in glTexStorage2D", "Failed to create an offscreen framebuffer"))]
    if errors: raise RuntimeError("\n".join(errors))
    for line in log.splitlines():
        if "NATIVE_GLASS_PASSED" in line: print(line)
    print("Native compositor: animated blur produced no invalid framebuffer")


def desktop():
    from gi.repository import Gio, GLib

    home = Path(os.environ["HOME"])
    package = Path(os.environ["XDG_DATA_HOME"]) / "plasma/plasmoids" / ID
    package.parent.mkdir(parents=True)
    shutil.copytree(ROOT / "build/plasma", package)
    apps = Path(os.environ["XDG_DATA_HOME"]) / "applications"
    apps.mkdir(parents=True)
    for name, icon in (("terminal", "utilities-terminal"), ("files", "system-file-manager"), ("calculator", "accessories-calculator"), ("four", "utilities-terminal")):
        (apps / f"test.{name}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name.title()}\nIcon={icon}\n"
            f"Exec=/usr/bin/kdialog --desktopfile test.{name} --title {name.title()} --msgbox 'Native window tracking'\n")
    config = Path(os.environ["XDG_CONFIG_HOME"])
    config.mkdir(exist_ok=True)
    (config / "kdeglobals").write_text("[General]\nColorScheme=BreezeDark\n[Colors:Window]\nBackgroundNormal=35,38,41\nForegroundNormal=239,240,241\n")
    source = Gio.SettingsSchemaSource.new_from_directory(str(package / "contents/schemas"), Gio.SettingsSchemaSource.get_default(), False)
    settings = Gio.Settings.new_full(source.lookup("org.gnome.shell.extensions.dock-groups", False), None, None)
    settings.set_string("groups", json.dumps({"test": {"id": "local.groups.test", "name": "Tools", "icon": "folder",
        "colors": ["#40505c", "#263d4a"], "apps": [{"desktop": f"test.{name}.desktop", "label": name.title(), "aliases": ["org.kde.kdialog.desktop"] if name == "terminal" else []} for name in ("terminal", "files", "calculator")]}}))
    settings.set_strv("plasma-favorites", ["local.groups.test.desktop"])
    settings.set_boolean("plasma-initialized", True)
    if "--ui" in sys.argv:
        from plasma_layout_fixture import prepare
        prepare(settings, apps)
    Gio.Settings.sync()
    subprocess.run(["kbuildsycoca6", "--noincremental"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    qml = package / "contents/ui/main.qml"
    text = instrument(qml.read_text(), "--interaction" in sys.argv)
    if "--interaction" in sys.argv:
        settings.set_string("groups", "{}")
        settings.set_strv("plasma-favorites", [f"test.{name}.desktop" for name in ("terminal", "files", "calculator")])
        Gio.Settings.sync()
    if "--visual" in sys.argv:
        text = text.replace('popup.visualParent = root.fullRepresentationItem;',
            'popup.visualParent = root.fullRepresentationItem.children[0].children.find(item => item.objectName === "local.groups.test.desktop");')
        text = text.replace('root.activate("test.terminal.desktop");', 'popup.open();')
        text = text.replace('folderSettings.show();', 'console.log("GLASS_READY", popup.blur.enabled, popup.genie);')
    if "--ui" in sys.argv:
        import plasma_ui_checks
        text = plasma_ui_checks.instrument(qml.read_text())
        config_qml = package / "contents/ui/ConfigGeneral.qml"
        config_qml.write_text(plasma_ui_checks.instrument_settings(config_qml.read_text()))
        folder_qml = package / "contents/ui/FolderSettings.qml"
        folder_qml.write_text(plasma_ui_checks.instrument_folder(folder_qml.read_text()))
    if "--glass" in sys.argv:
        import plasma_glass_checks
        text = plasma_glass_checks.instrument(qml.read_text())
        settings_qml = package / "contents/ui/FolderSettings.qml"
        settings_qml.write_text(settings_qml.read_text().replace("    id: window", """    id: window
    function setTestTransparency(value) { tabs.currentIndex=1; popupOpacity.value=value; popupOpacity.moved(); }"""))
        if "--presented" in sys.argv:
            import plasma_animation_checks
            text = plasma_animation_checks.instrument(text)
            transition_qml = package / "contents/ui/FolderTransition.qml"
            transition_qml.write_text(plasma_animation_checks.instrument_transition(transition_qml.read_text()))
    if "--contrast" in sys.argv:
        import plasma_contrast_checks
        text = plasma_contrast_checks.instrument(qml.read_text())
    qml.write_text(text)
    if "--interaction" in sys.argv:
        icon_qml = package / "contents/ui/ApplicationIcon.qml"
        icon_qml.write_text(icon_qml.read_text().replace("    id: button", '    id: button\n    onToolTipVisibleChanged: shown => console.log("NATIVE_TOOLTIP", button.desktop, shown)'))
    backend_type = os.environ["DOCK_FOLDERS_TEST_PLASMA_BACKEND"]
    env = dict(os.environ, QT_QPA_PLATFORM="wayland" if backend_type == "wayland" else "xcb",
               XDG_SESSION_TYPE=backend_type, WAYLAND_DISPLAY="dock-folders-review" if backend_type == "wayland" else "")
    update_activation_environment(env)
    backend = subprocess.Popen(["/usr/bin/python3", str(package / "contents/code/service.py")], env=env)
    with (home / "shell.log").open("w+") as output:
        shell = subprocess.Popen(["plasmashell", "--no-respawn"], env=env, stdout=output, stderr=output)
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            if "--lifecycle" in sys.argv:
                import plasma_lifecycle
                plasma_lifecycle.run(connection, settings, apps)
                return
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    result = connection.call_sync("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript",
                        GLib.Variant("(s)", (f"var p=panels()[0]; if(p){{p.height=64;var w=p.addWidget('{ID}');w.currentConfigGroup=['General'];w.writeConfig('placementBefore',p.widgets()[2].id);w.writeConfig('animation',1);w.reloadConfig();print(w.id);}}",)),
                        None, Gio.DBusCallFlags.NONE, 2000, None)
                    if result.unpack()[0].strip():
                        widget_id = result.unpack()[0].strip()
                        break
                except GLib.Error:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("Native Plasma panel did not start")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                result = connection.call_sync("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript",
                    GLib.Variant("(s)", ("var p=panels()[0];p.currentConfigGroup=['General'];print(p.readConfig('AppletOrder',''));",)),
                    None, Gio.DBusCallFlags.NONE, 2000, None)
                order = result.unpack()[0].strip().split(';')
                if len(order) > 2 and order[2] == widget_id:
                    break
                time.sleep(.1)
            else:
                print(Path(output.name).read_text())
                raise RuntimeError("The widget did not replace the task manager position: " + str(order))
            time.sleep(.5)
            if "--interaction" in sys.argv:
                from plasma_interaction import interaction
                interaction(output, connection, settings)
            elif "--contrast" in sys.argv:
                plasma_contrast_checks.verify(output, ROOT.parent)
            elif "--ui" in sys.argv:
                plasma_ui_checks.verify(output, ROOT.parent)
            elif "--glass" in sys.argv:
                plasma_glass_checks.verify(output, ROOT.parent)
            elif "--visual" in sys.argv:
                from PIL import ImageGrab
                time.sleep(3.4)
                ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(ROOT.parent / "plasma-material-glass-review.png")
                time.sleep(4.6)
            else:
                time.sleep(8)
            output.flush()
            log = Path(output.name).read_text()
            print(log)
            passed = "NATIVE_CONTRAST_PASSED" in log if "--contrast" in sys.argv else "NATIVE_UI_PASSED" in log if "--ui" in sys.argv else "NATIVE_GLASS_PASSED" in log if "--glass" in sys.argv else "GLASS_READY true true" in log if "--visual" in sys.argv else "NATIVE_INTERACTION_PASSED" in log if "--interaction" in sys.argv else "NATIVE_PANEL_READY 1" in log and "NATIVE_WINDOW_DOT true" in log
            if shell.poll() is not None or not passed:
                raise RuntimeError("Native Plasma panel check failed")
            own_errors = [line for line in log.splitlines() if ID in line and any(error in line for error in
                          ("TypeError", "ReferenceError", "Cannot assign", "Unable to assign", "Binding loop", "unavailable"))]
            if own_errors:
                raise RuntimeError("\n".join(own_errors))
        finally:
            if shell.poll() is None and any(mode in sys.argv for mode in ("--lifecycle", "--interaction", "--ui", "--glass")):
                print(Path(output.name).read_text()[-15000:])
            shell.terminate()
            shell.wait(timeout=5)
            backend.terminate()
            backend.wait(timeout=3)



if __name__ == "__main__":
    if "--desktop" in sys.argv:
        desktop()
    elif "--compositor" in sys.argv:
        compositor()
    else:
        main()

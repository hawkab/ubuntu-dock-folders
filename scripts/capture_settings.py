#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Capture native English settings in a disposable X11 session."""

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from session_runner import run_isolated

ROOT = Path(__file__).resolve().parent.parent


def wait_compositor():
    """Wait for the private compositor before GTK chooses its window visuals."""
    xlib = ctypes.CDLL("libX11.so.6")
    xlib.XOpenDisplay.argtypes, xlib.XOpenDisplay.restype = [ctypes.c_char_p], ctypes.c_void_p
    xlib.XInternAtom.argtypes, xlib.XInternAtom.restype = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int], ctypes.c_ulong
    xlib.XGetSelectionOwner.argtypes, xlib.XGetSelectionOwner.restype = [ctypes.c_void_p, ctypes.c_ulong], ctypes.c_ulong
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = xlib.XOpenDisplay(os.environ["DISPLAY"].encode())
    if not display:
        raise RuntimeError("The private X11 display is unavailable")
    try:
        atom = xlib.XInternAtom(display, b"_NET_WM_CM_S0", 0)
        deadline = time.monotonic() + 5
        while not xlib.XGetSelectionOwner(display, atom):
            if time.monotonic() >= deadline:
                raise RuntimeError("The private X11 compositor did not start")
            time.sleep(.03)
    finally:
        xlib.XCloseDisplay(display)


def center_window(window_id, width=None, height=None):
    """Ask the private X11 window manager to center the displayed window."""
    assert os.environ.get("DOCK_FOLDERS_TEST_SESSION")
    from PIL import ImageGrab
    screen = ImageGrab.grab(xdisplay=os.environ["DISPLAY"])
    if width is None or height is None:
        geometry = subprocess.check_output(["xwininfo", "-id", str(window_id)], text=True)
        width, height = [int(re.search(label + r":\s+(-?\d+)", geometry).group(1)) for label in ("Width", "Height")]

    class Message(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                    ("display", ctypes.c_void_p), ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
                    ("format", ctypes.c_int), ("data", ctypes.c_long * 5)]

    class Event(ctypes.Union):
        _fields_ = [("message", Message), ("padding", ctypes.c_long * 24)]

    xlib = ctypes.CDLL("libX11.so.6")
    xlib.XOpenDisplay.argtypes, xlib.XOpenDisplay.restype = [ctypes.c_char_p], ctypes.c_void_p
    xlib.XDefaultRootWindow.argtypes, xlib.XDefaultRootWindow.restype = [ctypes.c_void_p], ctypes.c_ulong
    xlib.XInternAtom.argtypes, xlib.XInternAtom.restype = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int], ctypes.c_ulong
    xlib.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.POINTER(Event)]
    xlib.XFlush.argtypes = xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = xlib.XOpenDisplay(os.environ["DISPLAY"].encode())
    if not display:
        raise RuntimeError("The private X11 display is unavailable")
    try:
        event = Event()
        event.message = Message(type=33, send_event=1, display=display, window=int(str(window_id), 0),
            message_type=xlib.XInternAtom(display, b"_NET_MOVERESIZE_WINDOW", 0), format=32,
            data=(ctypes.c_long * 5)((1 << 8) | (1 << 9) | (1 << 12),
                                    (screen.width - width) // 2, (screen.height - height) // 2, 0, 0))
        xlib.XSendEvent(display, xlib.XDefaultRootWindow(display), False, (1 << 19) | (1 << 20), ctypes.byref(event))
        xlib.XFlush(display)
        time.sleep(.15)
    finally:
        xlib.XCloseDisplay(display)


def capture_window(window_id, destination, *, center=True):
    """Capture the native window and its desktop context without resampling."""
    from PIL import ImageGrab
    geometry = subprocess.check_output(["xwininfo", "-id", str(window_id)], text=True)
    values = [int(re.search(label + r":\s+(-?\d+)", geometry).group(1)) for label in
              ("Absolute upper-left X", "Absolute upper-left Y", "Width", "Height")]
    x, y, width, height = values
    if center:
        center_window(window_id, width, height)
        from gi.repository import GLib
        deadline = time.monotonic() + .25
        context = GLib.MainContext.default()
        while time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(.01)
    geometry = subprocess.check_output(["xwininfo", "-id", str(window_id)], text=True)
    x, y = [int(re.search(label + r":\s+(-?\d+)", geometry).group(1)) for label in
            ("Absolute upper-left X", "Absolute upper-left Y")]
    frame = subprocess.check_output(["xprop", "-id", str(window_id), "_NET_FRAME_EXTENTS"], text=True)
    extents = re.search(r"=\s+(\d+), (\d+), (\d+), (\d+)", frame)
    left, right, top, bottom = map(int, extents.groups()) if extents else (0, 0, 0, 0)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image = ImageGrab.grab(xdisplay=os.environ["DISPLAY"])
    scale = int(os.environ.get("DOCK_FOLDERS_CAPTURE_SCALE", "1"))
    canvas_height = min(image.height, max(900 * scale, height + top + bottom + 140 * scale))
    canvas_y = min(max(0, y - top - (canvas_height - height - top - bottom) // 2), image.height - canvas_height)
    image = image.crop((0, canvas_y, image.width, canvas_y + canvas_height))
    image.save(destination)
    print(f"CAPTURED {destination.relative_to(ROOT)} {image.width}x{image.height} native scale {scale}", flush=True)


def set_background():
    """Render the original documentation's vector wallpaper on the private root."""
    from PIL import ImageGrab
    import cairo
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    width, height = ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).size
    wallpaper = Path(os.environ["HOME"]) / "documentation-background.png"
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    context = cairo.Context(surface)
    scale = max(width / 1440, height / 900)
    context.translate((width - 1440 * scale) / 2, (height - 900 * scale) / 2)
    context.scale(scale, scale)
    viewport = Rsvg.Rectangle()
    viewport.x = viewport.y = 0
    viewport.width, viewport.height = 1440, 900
    Rsvg.Handle.new_from_file(str(ROOT / "scripts/assets/demo-background.svg")).render_document(context, viewport)
    surface.write_to_png(str(wallpaper))
    properties = [("/desktop-icons/style", "int", "0")]
    for monitor in ("screen", "0"):
        prefix = f"/backdrop/screen0/monitor{monitor}/workspace0"
        properties.extend(((prefix + "/last-image", "string", str(wallpaper)),
                           (prefix + "/image-style", "int", "3")))
    for path, kind, value in properties:
        subprocess.run(["xfconf-query", "-c", "xfce4-desktop", "-p", path, "--create", "-t", kind, "-s", value],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.Popen(["xfdesktop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def sample_settings(settings, data):
    """Create sample folders and applications only in the private home."""
    from gi.repository import Gio
    apps = data / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    sample = [("chrome", "Google Chrome", "google-chrome"), ("firefox", "Firefox", "firefox"),
              ("terminal", "Terminal", "utilities-terminal"),
              ("files", "Files", "system-file-manager"), ("calculator", "Calculator", "accessories-calculator")]
    for id, label, icon in sample:
        (apps / f"sample.{id}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={label}\nExec=true\nIcon={icon}\n")
    groups = {}
    for key, name, ids in (("browsers", "Browsers", sample[:2]), ("tools", "Tools", sample[2:])):
        groups[key] = {"id": f"local.groups.{key}", "name": name, "icon": "folder",
            "dockColor": "#496b83", "dockOpacity": .2, "popupColor": "#263d4a",
            "backgroundOpacity": .2, "blurStrength": 70, "showLabel": False,
            "apps": [{"desktop": f"sample.{id}.desktop", "label": label} for id, label, _ in ids]}
    settings.set_string("groups", json.dumps(groups))
    settings.set_int("hover-orbit-speed", 999)
    settings.set_string("hover-effect", "rotate-cards")
    for key in ("plasma-favorites", "xfce-favorites"):
        settings.set_strv(key, ["local.groups.browsers.desktop"])
    settings.set_boolean("plasma-initialized", True)
    Gio.Settings.new("org.gnome.shell").set_strv("favorite-apps", ["local.groups.browsers.desktop"])
    Gio.Settings.sync()
    return groups


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from descendants(child)
        child = child.get_next_sibling()


def gtk_session(desktop):
    app_path = ROOT / ("build/xfce/shared/app" if desktop == "xfce" else "build/extension/app")
    sys.path.insert(0, str(app_path))
    import preferences as preferences
    from global_preferences import build_global_window
    from gi.repository import Adw, GdkX11, GLib, Gtk
    preferences.Adw.init()
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
    groups = sample_settings(preferences.SETTINGS, Path(os.environ["XDG_DATA_HOME"]))
    destination = ROOT / "docs" / ("xfce" if desktop == "xfce" else "")

    def settle(milliseconds=750):
        loop = GLib.MainLoop()
        GLib.timeout_add(milliseconds, lambda: loop.quit() or False)
        loop.run()

    def capture(window, name):
        settle()
        surface = window.get_surface()
        capture_window(GdkX11.X11Surface.get_xid(surface), destination / name)
        if name == "general-settings.png":
            speeds = [item for item in descendants(window) if isinstance(item, Gtk.Scale)
                      and item.get_adjustment().get_upper() == 999]
            assert speeds and all(item.get_adjustment().get_lower() == -999 for item in speeds)
            assert preferences.SETTINGS.get_int("hover-orbit-speed") == 999
            print(f"SPEED_RANGE_OK {desktop} -999..999", flush=True)

    for tab, height, name in (("dock", 1240, "general-settings.png"),
                             ("popup", 850, "general-settings-open.png"),
                             ("folders", 620, "existing-folders.png" if desktop == "xfce" else "app-grid-folders.png")):
        window = build_global_window(tab=tab, desktop=desktop)
        window.set_default_size(760, height)
        window.present()
        capture(window, name)
        window.close()
        settle(100)
    application = preferences.Preferences("browsers")
    folder = application.group_window(groups["browsers"])
    folder.set_default_size(680, 860)
    folder.present()
    stack = next(item for item in descendants(folder) if isinstance(item, Gtk.Stack)
                 and item.get_child_by_name("dock"))
    capture(folder, "folder-settings-dock.png")
    stack.set_visible_child_name("popup")
    capture(folder, "folder-settings-open.png")
    folder.close()
    settle(100)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", choices=("gnome", "xfce", "plasma"), required=True)
    parser.add_argument("--session", action="store_true")
    parser.add_argument("--scale", type=int, choices=(1, 2), default=2)
    options = parser.parse_args()
    if options.session:
        wm = subprocess.Popen(["xfwm4", "--replace", "--compositor=on"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        background = None
        try:
            wait_compositor()
            background = set_background()
            if options.desktop == "plasma":
                from capture_plasma_settings import session
                session()
            else:
                gtk_session(options.desktop)
        finally:
            if background:
                background.terminate()
                background.wait(timeout=5)
            wm.terminate()
            wm.wait(timeout=5)
        return
    with tempfile.TemporaryDirectory(prefix="dock-folders-docs-") as directory:
        home = Path(directory)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
            XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
            XDG_STATE_HOME=str(home / "state"), GSETTINGS_BACKEND="keyfile", LANGUAGE="en",
            LC_ALL="C.UTF-8", GDK_BACKEND="x11", GTK_A11Y="none", QT_QPA_PLATFORM="xcb",
            QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="org.kde.desktop",
            XDG_CURRENT_DESKTOP={"plasma": "KDE", "xfce": "XFCE", "gnome": "GNOME"}[options.desktop],
            XDG_SESSION_TYPE="x11", WAYLAND_DISPLAY="", GIO_USE_VFS="local", NO_AT_BRIDGE="1",
            XDG_DATA_DIRS="/usr/local/share:/usr/share")
        scale = options.scale
        env.update(GDK_SCALE=str(scale), QT_SCALE_FACTOR=str(scale), DOCK_FOLDERS_CAPTURE_SCALE=str(scale),
                   GSK_RENDERER="cairo", LIBGL_ALWAYS_SOFTWARE="1", LP_NUM_THREADS="2")
        if options.desktop == "plasma":
            env.pop("QT_QUICK_BACKEND", None)
            env.update(QSG_RHI_BACKEND="opengl", QSG_INFO="1")
        run_isolated(["xvfb-run", "-a", "-s", f"-screen 0 {1440 * scale}x{1400 * scale}x24", "/usr/bin/python3",
                      str(Path(__file__).resolve()), "--session", "--desktop", options.desktop,
                      "--scale", str(scale)], env, 65)


if __name__ == "__main__":
    main()

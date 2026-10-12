# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Capture a bounded backdrop through the active display's screenshot API."""

import shutil
import subprocess
from gi.repository import Gdk, GdkPixbuf, Gio, GLib


def capture_async(x, y, width, height, native, ready):
    """Capture raw pixels without waiting for a Wayland subprocess in GTK's event loop."""
    if not native:
        ready(capture(x,y,width,height))
        return None
    if width <= 0 or height <= 0 or width*height > 16777216 or not shutil.which("grim"):
        ready(None)
        return None
    try:
        process = Gio.Subprocess.new(["grim","-t","ppm","-s","1","-g",f"{x},{y} {width}x{height}","-"],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)
    except GLib.Error:
        ready(None)
        return None
    deadline = GLib.timeout_add(800,lambda: (process.force_exit(),GLib.SOURCE_REMOVE)[1])

    def finished(worker, result):
        nonlocal deadline
        if GLib.MainContext.default().find_source_by_id(deadline): GLib.source_remove(deadline)
        deadline = 0
        pixbuf = None
        try:
            success,stdout,_stderr = worker.communicate_finish(result)
            if success and worker.get_successful():
                loader = GdkPixbuf.PixbufLoader.new_with_type("pnm")
                loader.write(stdout.get_data())
                loader.close()
                pixbuf = loader.get_pixbuf()
        except GLib.Error:
            pass
        ready(pixbuf)

    process.communicate_async(None,None,finished)
    return process


def capture(x, y, width, height, native=False):
    if not native:
        return Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), x, y, width, height)
    if not shutil.which("grim"):
        return None
    try:
        result = subprocess.run(["grim", "-t", "ppm", "-s", "1", "-g", f"{x},{y} {width}x{height}", "-"],
                                capture_output=True, timeout=.8, check=True)
        loader = GdkPixbuf.PixbufLoader.new_with_type("pnm")
        loader.write(result.stdout)
        loader.close()
        return loader.get_pixbuf()
    except (subprocess.SubprocessError, OSError, GLib.Error):
        return None

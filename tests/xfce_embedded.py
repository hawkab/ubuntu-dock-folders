# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Repeat pointer regressions through the native GtkSocket/Plug boundary."""

import os
import sys
from panel import Controller, Gdk, Gtk
from xfce_pointer import check_gestures


def check_embedded(wait, settle):
    host=Gtk.Window(title="Native panel socket")
    host.set_decorated(False)
    host.set_type_hint(Gdk.WindowTypeHint.DOCK)
    host.set_skip_taskbar_hint(True)
    socket=Gtk.Socket()
    host.add(socket)
    host.show_all()
    reader,writer=os.pipe()
    previous=sys.stdin
    with os.fdopen(reader,"r") as stream:
        sys.stdin=stream
        controller=Controller(socket.get_id(),size=48)
        controller.test_host=host
        settle()
        try:
            check_gestures(controller,None,wait,settle)
        finally:
            controller.window.destroy()
            host.destroy()
            sys.stdin=previous
            os.close(writer)
    print("Xfce: embedded pointer regrouping and folder switching passed.")

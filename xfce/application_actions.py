# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Launch, focus and cycle applications through the selected window adapter."""

from gi.repository import Gdk, Gtk
from windows import desktop_info
import logging


class ApplicationActions:
    def application_press(self, button, event, desktop, group):
        logging.getLogger("ubuntu-dock-folders.xfce").debug("Application press %s", desktop)
        if event.button == 2 and not group:
            self.activate(desktop, True)
            return True
        return self.context_menu(button,event,desktop,group)

    def application_scroll(self, _button, event, desktop, group):
        if group or event.direction not in (Gdk.ScrollDirection.UP,Gdk.ScrollDirection.DOWN):
            return False
        windows = self.windows.get(desktop, [])
        index = self.state.core.call("cycle", {"windows":[{"active":window.is_active()} for window in windows],
            "direction":-1 if event.direction == Gdk.ScrollDirection.UP else 1})
        if index >= 0:
            self.activate_window(windows[index])
        return True

    def activate_window(self, window):
        if hasattr(window, "activate_workspace"):
            window.activate_workspace(Gtk.get_current_event_time())
        else:
            workspace = window.get_workspace()
            if workspace:
                workspace.activate(Gtk.get_current_event_time())
        window.activate(Gtk.get_current_event_time())

    def activate(self, desktop, new_instance=False):
        windows = self.windows.get(desktop, [])
        decision = self.state.core.call("activation", {"windows":[{"active":window.is_active(),
            "minimized":window.is_minimized()} for window in windows], "newInstance":new_instance})
        if decision["action"] == "launch":
            info = desktop_info(desktop)
            if info:
                info.launch([], Gdk.Display.get_default().get_app_launch_context())
        elif decision["action"] == "minimize":
            windows[decision["index"]].minimize()
        else:
            self.activate_window(windows[decision["index"]])
        if self.popup:
            self.popup.close()

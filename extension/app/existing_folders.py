# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Select saved groups and app-grid folders for the current desktop panel."""

import sys
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk
from settings import ROOT, SETTINGS
from i18n import _, set_ui_direction
from window_lifecycle import on_window_close
sys.path.insert(0, str(ROOT / "adapters"))
from runtime import CoreRuntime
from folder_library import FolderLibrary

__all__ = ("SETTINGS", "attach_existing_folders", "launch_existing_folders")


def attach_existing_folders(builder, settings, window, desktop, core=None):
    """Embed live folder selections and release all watches on window close."""
    owns_core = core is None
    core = core or CoreRuntime(ROOT)
    library = FolderLibrary(settings, desktop, core.call)
    section = builder.get_object("existing_folders_group")
    rows, refresh_timer, closed, error = [], 0, False, ""

    def refresh():
        nonlocal refresh_timer
        refresh_timer = 0
        if closed or not section.get_mapped():
            return GLib.SOURCE_REMOVE
        for row in rows:
            section.remove(row)
        rows.clear()
        if error:
            row=Adw.ActionRow(title=error,use_markup=False)
            section.add(row)
            rows.append(row)
        try:
            catalog = library.catalog()
        except (RuntimeError, ValueError, TimeoutError, OSError) as failure:
            row = Adw.ActionRow(title=str(failure), use_markup=False)
            section.add(row)
            rows.append(row)
            return GLib.SOURCE_REMOVE
        if not catalog:
            row = Adw.ActionRow(title=_("No folders available"), use_markup=False)
            section.add(row)
            rows.append(row)
        for item in catalog:
            row = Adw.ActionRow(title=item["name"], subtitle=" · ".join(app["label"] for app in item["apps"][:3]), use_markup=False)
            row.set_name(item["id"])
            row.add_prefix(Gtk.Image(icon_name="folder-symbolic"))
            button = Gtk.ToggleButton(label=_("Pinned") if item["pinned"] else _("Pin to panel"),
                active=item["pinned"], sensitive=(item["enabled"] and settings.get_boolean("enabled")) or item["pinned"], valign=Gtk.Align.CENTER)
            button.set_tooltip_text(_("Unpin from panel") if item["pinned"] else _("Pin to panel"))

            def toggled(button, id=item["id"]):
                nonlocal error
                try:
                    library.pin(id, button.get_active())
                    error=""
                except (RuntimeError, ValueError, TimeoutError, OSError) as failure:
                    error=str(failure)
                finally:
                    queue_refresh()

            button.connect("toggled", toggled)
            row.add_suffix(button)
            section.add(row)
            rows.append(row)
        return GLib.SOURCE_REMOVE

    def queue_refresh(*_args):
        nonlocal refresh_timer
        if not closed and not refresh_timer and section.get_mapped():
            refresh_timer = GLib.idle_add(refresh)

    monitor = Gio.AppInfoMonitor.get()
    signals = [(settings, settings.connect("changed::groups", queue_refresh)),
               (settings, settings.connect("changed::enabled", queue_refresh)),
               (monitor, monitor.connect("changed", queue_refresh))]
    if library.favorites_store:
        signals.append((library.favorites_store, library.favorites_store.connect("changed::" + library.favorites_key, queue_refresh)))
    library.sources.watch(queue_refresh)

    def close(_window):
        nonlocal closed, refresh_timer
        closed = True
        if refresh_timer:
            GLib.source_remove(refresh_timer)
            refresh_timer = 0
        for settings, signal in signals:
            settings.disconnect(signal)
        signals.clear()
        library.sources.close()
        if owns_core:
            core.close()
        return False

    on_window_close(window, close)
    section.connect("map", queue_refresh)


def launch_existing_folders():
    """Open global preferences at the existing folders tab."""
    from preferences import Preferences
    set_ui_direction()
    return Preferences(None, tab="folders").run()


if __name__ == "__main__":
    launch_existing_folders()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Build appearance controls and save each change immediately."""

import gi
import json
import os
import sys
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from i18n import _
from settings import ROOT, SETTINGS, groups
from folder_window import build_folder_window
from window_lifecycle import on_window_close
sys.path.insert(0, str(ROOT / "adapters"))
from runtime import CoreRuntime

class FolderAppearance:
    """Provide appearance rows and previews for a selected folder."""
    def appearance_range(self, name):
        return next(item["range"] for item in self.core.call("contract")["appearancePreferences"] if item["name"] == name)

    def surface(self, group):
        return self.core.call("surface", {"group":group, "blurStrength":SETTINGS.get_int("blur-strength"),
                                          "legacyGlass":SETTINGS.get_boolean("glass")})

    def save(self, field, value):
        current = groups()
        if self.key not in current:
            return
        result = self.core.call("transaction", {"state": {"groups": current, "favorites": [], "undo": None},
            "command": {"operation": "appearance", "key": self.key, "property": field, "value": value}})
        if not result["changed"]:
            return
        current = result["state"]["groups"]
        SETTINGS.set_string("groups", json.dumps(current, ensure_ascii=False))
        Gio.Settings.sync()
        self.refresh_previews(current[self.key])


    def refresh_previews(self, group):
        for preview in getattr(self, "folder_previews", []):
            preview.update(group)
        if hasattr(self, "window_title"):
            self.window_title.set_subtitle(group["name"])
            self.appearance_window.set_title(f"{_('Folder appearance')} — {group['name']}")
        if hasattr(self, "popup_adjustment"):
            opacity = self.surface(group)["backgroundOpacity"]
            self.popup_adjustment.handler_block(self.popup_changed)
            self.popup_adjustment.set_value(round((1 - opacity) * 100))
            self.popup_adjustment.handler_unblock(self.popup_changed)

    def apply_to_all(self):
        """Copy the selected folder's appearance, preserving names and applications."""
        current = groups()
        result = self.core.call("transaction", {
            "state": {"groups": current, "favorites": [], "undo": None},
            "command": {"operation": "applyAppearance", "key": self.key,
                        "blurStrength": SETTINGS.get_int("blur-strength"),
                        "legacyGlass": SETTINGS.get_boolean("glass")},
        })
        if result["changed"]:
            SETTINGS.set_string("groups", json.dumps(result["state"]["groups"], ensure_ascii=False))
            Gio.Settings.sync()

    def confirm_apply_to_all(self, window):
        """Ask before replacing the appearance of other folders."""
        dialog = Adw.MessageDialog(
            transient_for=window, modal=True,
            heading=_("Replace other folders’ appearance?"),
            body=_("This will overwrite the custom appearance settings of all other folders. Names and applications will stay the same."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("apply", _("Apply to all folders"))
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _dialog, response: self.apply_to_all() if response == "apply" else None)
        dialog.present()
        return dialog


    def color_row(self, group, field, title, default):
        row = Adw.ActionRow(title=title)
        rgba = Gdk.RGBA()
        rgba.parse(group.get(field, default))
        picker = Gtk.ColorDialogButton(
            dialog=Gtk.ColorDialog(title=title, with_alpha=False),
            rgba=rgba,
            valign=Gtk.Align.CENTER,
        )
        picker.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [
                _("Dock icon background color")
                if field == "dockColor"
                else _("Open folder background color")
            ],
        )

        def selected(button, _param):
            rgba = button.get_rgba()
            self.save(
                field,
                "#%02x%02x%02x" % tuple(round(v * 255) for v in (rgba.red, rgba.green, rgba.blue)),
            )

        picker.connect("notify::rgba", selected)
        row.add_suffix(picker)
        row.set_activatable_widget(picker)
        return row


    def transparency_row(self, field, opacity):
        row = Adw.PreferencesRow(title=_("Transparency"), activatable=False)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            margin_start=16,
            margin_end=16,
            margin_top=10,
            margin_bottom=10,
        )
        heading = Gtk.Box(spacing=6)
        title = Gtk.Label(
            label=_("Transparency"),
            xalign=0,
            hexpand=True,
        )
        heading.append(title)
        adjustment = Gtk.Adjustment(
            value=round((1 - opacity) * 100),
            lower=0,
            upper=100,
            step_increment=1,
            page_increment=10,
        )
        number = Gtk.SpinButton(
            adjustment=adjustment, digits=0, numeric=True, width_chars=3, valign=Gtk.Align.CENTER
        )
        accessible = (
            _("Dock icon transparency") if field == "dockOpacity" else _("Open folder transparency")
        )
        number.update_property([Gtk.AccessibleProperty.LABEL], [_("%s, percent") % accessible])
        heading.append(number)
        heading.append(Gtk.Label(label="%"))
        box.append(heading)
        slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=adjustment,
            draw_value=False,
            hexpand=True,
        )
        slider.update_property([Gtk.AccessibleProperty.LABEL], [accessible])
        box.append(slider)
        ends = Gtk.Box()
        for label, align in ((_("Opaque"), 0), (_("Transparent"), 1)):
            end = Gtk.Label(label=label, xalign=align, hexpand=True)
            end.add_css_class("caption")
            end.add_css_class("dim-label")
            ends.append(end)
        box.append(ends)
        row.set_child(box)
        changed = adjustment.connect(
            "value-changed",
            lambda a: self.save(
                field,
                round(1 - round(a.get_value()) / 100, 2),
            ),
        )
        if field == "backgroundOpacity":
            self.popup_adjustment, self.popup_changed = adjustment, changed
            self.popup_transparency_label = title
        return row


    def open_system_settings(self, window):
        try:
            integration = ROOT / "integration/ubuntu-settings"
            command = (
                [str(integration), "ubuntu", "dock-groups"]
                if integration.exists()
                else ["gnome-extensions", "prefs", "dock-groups@local"]
            )
            if os.environ.get("DOCK_FOLDERS_DESKTOP") == "xfce" or "xfce" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
                command = ["/usr/bin/python3", str(ROOT / "app/preferences.py"), "--global"]
            Gio.Subprocess.new(command, Gio.SubprocessFlags.NONE)
        except GLib.Error as error:
            message = Adw.MessageDialog(
                transient_for=window,
                modal=True,
                heading=_("Could not open system settings"),
                body=str(error),
            )
            message.add_response("close", _("Close"))
            message.present()


    def group_window(self, group):
        self.core = CoreRuntime(ROOT)
        window = build_folder_window(self, self.surface(group))
        on_window_close(window, lambda _window: self.core.close())
        return window

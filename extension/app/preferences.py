#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Native GTK4/Adwaita preferences, sharing settings with the Shell extension."""

import hashlib
import json
import shutil
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from folder_preview import FolderPreview
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from i18n import DOMAIN, _, set_ui_direction
from settings import DATA, ROOT, SETTINGS, groups

IMAGE_FORMATS = (
    ("PNG", ("png",), "image/png"),
    ("JPEG", ("jpg", "jpeg"), "image/jpeg"),
    ("BMP", ("bmp",), "image/bmp"),
    ("WebP", ("webp",), "image/webp"),
    ("GIF", ("gif",), "image/gif"),
    ("SVG", ("svg",), "image/svg+xml"),
)


def wallpaper_filters():
    filters = Gio.ListStore.new(Gtk.FileFilter)
    all_images = Gtk.FileFilter(name=_("All images — PNG, JPEG, BMP, WebP, GIF, SVG"))
    filters.append(all_images)
    for name, extensions, mime in IMAGE_FORMATS:
        format_filter = Gtk.FileFilter(
            name=name + " (" + ", ".join("*." + ext for ext in extensions) + ")"
        )
        for filter_ in (all_images, format_filter):
            filter_.add_mime_type(mime)
            for extension in extensions:
                filter_.add_pattern("*." + extension)
                filter_.add_pattern("*." + extension.upper())
        filters.append(format_filter)
    all_files = Gtk.FileFilter(name=_("All files"))
    all_files.add_pattern("*")
    filters.append(all_files)
    return filters, all_images


class Preferences(Adw.Application):
    def __init__(self, key):
        super().__init__(
            application_id="local.groups.Preferences", flags=Gio.ApplicationFlags.NON_UNIQUE
        )
        self.key = key
        self.connect("activate", self.activate_window)

    def activate_window(self, _app):
        if self.key is None:
            builder = Gtk.Builder()
            builder.set_translation_domain(DOMAIN)
            builder.add_from_file(str(ROOT / "preferences.ui"))
            window = builder.get_object("preferences_window")
            for key in ("enabled", "customization", "glass"):
                SETTINGS.bind(
                    key, builder.get_object(key + "_row"), "active", Gio.SettingsBindFlags.DEFAULT
                )
            for key in ("customization", "glass"):
                SETTINGS.bind(
                    "enabled",
                    builder.get_object(key + "_row"),
                    "sensitive",
                    Gio.SettingsBindFlags.GET,
                )
            grid = builder.get_object("grid_folders_row")
            SETTINGS.bind("enabled", grid, "sensitive", Gio.SettingsBindFlags.GET)
            grid.connect(
                "activated",
                lambda _row: Gio.Subprocess.new(
                    ["/usr/bin/python3", str(ROOT / "app/grid_folders.py")],
                    Gio.SubprocessFlags.NONE,
                ),
            )
            animation = builder.get_object("animation_row")
            SETTINGS.bind(
                "font-size",
                builder.get_object("font_size_row"),
                "value",
                Gio.SettingsBindFlags.DEFAULT,
            )
            animation.set_selected(int(SETTINGS.get_string("animation") == "flow"))
            animation.connect(
                "notify::selected",
                lambda row, _p: SETTINGS.set_string(
                    "animation", "flow" if row.get_selected() else "scale"
                ),
            )
        else:
            group = groups().get(self.key)
            if group is None:
                self.quit()
                return
            window = self.group_window(group)
            changed = SETTINGS.connect(
                "changed::glass", lambda _settings, _key: self.refresh_previews(groups()[self.key])
            )
            window.connect("destroy", lambda _window: SETTINGS.disconnect(changed))
        window.set_application(self)
        window.present()

    def save(self, field, value):
        current = groups()
        if self.key not in current:
            return
        current[self.key][field] = value
        SETTINGS.set_string("groups", json.dumps(current, ensure_ascii=False))
        Gio.Settings.sync()
        self.refresh_previews(current[self.key])

    def refresh_previews(self, group):
        for preview in getattr(self, "folder_previews", []):
            preview.glass = SETTINGS.get_boolean("glass")
            preview.update(group)
        if hasattr(self, "window_title"):
            self.window_title.set_subtitle(group["name"])
        if hasattr(self, "popup_adjustment"):
            glass = SETTINGS.get_boolean("glass")
            opacity = group.get("glassOpacity", 0.38) if glass else group.get("popupOpacity", 0.98)
            self.popup_adjustment.handler_block(self.popup_changed)
            self.popup_adjustment.set_value(round((1 - opacity) * 100))
            self.popup_adjustment.handler_unblock(self.popup_changed)
            self.popup_transparency_label.set_text(
                _("Glass tint transparency") if glass else _("Transparency")
            )
            self.glass_hint.set_visible(glass)

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
            label=_("Glass tint transparency")
            if field == "popupOpacity" and SETTINGS.get_boolean("glass")
            else _("Transparency"),
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
                "glassOpacity"
                if field == "popupOpacity" and SETTINGS.get_boolean("glass")
                else field,
                round(1 - round(a.get_value()) / 100, 2),
            ),
        )
        if field == "popupOpacity":
            self.popup_adjustment, self.popup_changed = adjustment, changed
            self.popup_transparency_label = title
        return row

    def group_window(self, group):
        window = Adw.Window(
            title=_("Folder appearance"), default_width=600, default_height=660, modal=True
        )
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.window_title = Adw.WindowTitle(title=_("Folder appearance"), subtitle=group["name"])
        header.set_title_widget(self.window_title)
        toolbar.add_top_bar(header)
        window.set_content(toolbar)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toolbar.set_content(layout)
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True,
        )
        layout.append(scroll)
        clamp = Adw.Clamp(maximum_size=560, tightening_threshold=440)
        scroll.set_child(clamp)
        body = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_start=24,
            margin_end=24,
            margin_top=12,
            margin_bottom=16,
        )
        clamp.set_child(body)
        general = Adw.PreferencesGroup()
        body.append(general)
        name = Adw.EntryRow(title=_("Name"), text=group["name"])

        def rename(row):
            value = row.get_text().strip()
            if value:
                self.save("name", value[:80])

        name.connect("changed", rename)
        general.add(name)
        stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=150,
            hhomogeneous=True,
            vhomogeneous=True,
        )
        switcher = Gtk.StackSwitcher(stack=stack, halign=Gtk.Align.CENTER)
        switcher.add_css_class("linked")
        body.append(switcher)
        body.append(stack)
        self.folder_previews = []
        pages = {}
        for mode, title in (("dock", _("On the dock")), ("popup", _("When opened"))):
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            preview = FolderPreview(
                group,
                mode,
                glass=SETTINGS.get_boolean("glass"),
                font_size=SETTINGS.get_double("font-size"),
            )
            preview.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [_("Dock icon preview") if mode == "dock" else _("Open folder preview")],
            )
            page.append(preview)
            self.folder_previews.append(preview)
            controls = Adw.PreferencesGroup()
            page.append(controls)
            pages[mode] = controls
            stack.add_titled(page, mode, title)
        opacity = group.get(
            "dockOpacity",
            (1.0 if group["transparentDock"] is False else 0.0)
            if "transparentDock" in group
            else 0.2,
        )
        pages["dock"].add(
            self.color_row(group, "dockColor", _("Background color"), group["colors"][1])
        )
        pages["dock"].add(self.transparency_row("dockOpacity", opacity))
        labels = Adw.SwitchRow(
            title=_("Label below the icon"), active=group.get("showLabel", False)
        )
        labels.connect("notify::active", lambda row, _p: self.save("showLabel", row.get_active()))
        pages["dock"].add(labels)
        pages["popup"].add(self.color_row(group, "popupColor", _("Background color"), "#26262a"))
        glass = SETTINGS.get_boolean("glass")
        pages["popup"].add(
            self.transparency_row(
                "popupOpacity",
                group.get("glassOpacity", 0.38) if glass else group.get("popupOpacity", 0.98),
            )
        )
        self.glass_hint = Gtk.Label(
            label=_("Material Glass: blurred background, translucent tint, and sharp icons."),
            wrap=True,
            xalign=0,
            visible=glass,
        )
        self.glass_hint.add_css_class("caption")
        self.glass_hint.add_css_class("dim-label")
        stack.get_child_by_name("popup").append(self.glass_hint)
        self.wallpaper_row = Adw.ActionRow(title=_("Wallpaper"))
        self.wallpaper_select = Gtk.Button(label=_("Choose…"), valign=Gtk.Align.CENTER)
        self.wallpaper_select.connect("clicked", lambda _button: self.choose_wallpaper(window))
        self.wallpaper_clear = Gtk.Button(
            icon_name="user-trash-symbolic",
            tooltip_text=_("Remove wallpaper"),
            valign=Gtk.Align.CENTER,
        )
        self.wallpaper_clear.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Remove wallpaper")]
        )
        self.wallpaper_clear.add_css_class("flat")
        self.wallpaper_clear.connect("clicked", lambda _button: self.set_wallpaper(""))
        self.wallpaper_row.add_suffix(self.wallpaper_select)
        self.wallpaper_row.add_suffix(self.wallpaper_clear)
        pages["popup"].add(self.wallpaper_row)
        self.update_wallpaper_row(group)
        system_settings = Gtk.Button(
            label=_("General folder settings"),
            halign=Gtk.Align.CENTER,
            margin_top=4,
            tooltip_text=_("Settings → Ubuntu Desktop → Dock → Dock folders"),
        )
        system_settings.add_css_class("flat")
        system_settings.get_child().add_css_class("accent")
        system_settings.connect("clicked", lambda _button: self.open_system_settings(window))
        layout.append(system_settings)
        status = Gtk.Label(
            label=_("Changes are saved automatically"), margin_top=4, margin_bottom=16
        )
        status.add_css_class("dim-label")
        status.add_css_class("caption")
        layout.append(status)
        window.set_focus(switcher.get_first_child())
        return window

    def open_system_settings(self, window):
        try:
            integration = ROOT / "integration/ubuntu-settings"
            command = (
                [str(integration), "ubuntu", "dock-groups"]
                if integration.exists()
                else ["gnome-extensions", "prefs", "dock-groups@local"]
            )
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

    def update_wallpaper_row(self, group):
        chosen = bool(group.get("wallpaper"))
        self.wallpaper_row.set_subtitle(
            group.get("wallpaperName") or _("Image selected")
            if chosen
            else "PNG, JPEG, BMP, WebP, GIF, SVG"
        )
        self.wallpaper_select.set_label(_("Replace…") if chosen else _("Choose…"))
        self.wallpaper_clear.set_visible(chosen)

    def set_wallpaper(self, filename, display_name=""):
        self.save("wallpaper", filename)
        self.save("wallpaperName", display_name)
        self.update_wallpaper_row(groups()[self.key])

    def choose_wallpaper(self, window):
        dialog = Gtk.FileDialog(title=_("Folder wallpaper"))
        filters, all_images = wallpaper_filters()
        dialog.set_filters(filters)
        dialog.set_default_filter(all_images)
        folder = groups().get(self.key, {}).get("wallpaperFolder") or GLib.get_user_special_dir(
            GLib.UserDirectory.DIRECTORY_PICTURES
        )
        if folder and Path(folder).is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(folder))

        def selected(dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error as error:
                if not error.matches(
                    Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED
                ) and not error.matches(Gtk.dialog_error_quark(), Gtk.DialogError.CANCELLED):
                    self.wallpaper_error(window, error)
                return
            filename = file.get_path()
            if not filename:
                return
            try:
                Gdk.Texture.new_from_file(file)
                content = Path(filename).read_bytes()
                directory = DATA / "wallpapers"
                directory.mkdir(parents=True, exist_ok=True)
                destination = directory / (
                    hashlib.sha256(content).hexdigest()[:20] + Path(filename).suffix.lower()
                )
                shutil.copyfile(filename, destination)
                self.set_wallpaper(str(destination), Path(filename).name)
                self.save("wallpaperFolder", str(Path(filename).parent))
            except (OSError, GLib.Error) as error:
                self.wallpaper_error(window, error)

        dialog.open(window, None, selected)

    def wallpaper_error(self, window, error):
        message = Adw.MessageDialog(
            transient_for=window, modal=True, heading=_("Could not open the image"), body=str(error)
        )
        message.add_response("close", _("Close"))
        message.present()


if __name__ == "__main__":
    key = None if len(sys.argv) < 2 or sys.argv[1] == "--global" else sys.argv[1]
    set_ui_direction()
    Preferences(key).run([sys.argv[0]])

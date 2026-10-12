# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Choose, validate, and copy a folder wallpaper."""

import sys
import shutil
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from i18n import _
from settings import DATA, groups
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent / 'adapters'))
from images import image_info, file_digest

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


class FolderWallpaper:
    """Provide a wallpaper chooser for the selected folder."""
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
                if Path(filename).stat().st_size > 20*1024*1024 or not image_info(filename):
                    raise OSError('Image exceeds the wallpaper size limit')
                Gdk.Texture.new_from_file(file)
                directory = DATA / "wallpapers"
                directory.mkdir(parents=True, exist_ok=True)
                destination = directory / (
                    file_digest(filename)[:20] + Path(filename).suffix.lower()
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

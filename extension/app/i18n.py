# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Gettext setup shared by the GTK applications."""

import gettext
import locale
from pathlib import Path

DOMAIN = "ubuntu-dock-folders"
LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"

try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    locale.setlocale(locale.LC_ALL, "C.UTF-8")

locale.bindtextdomain(DOMAIN, str(LOCALE_DIR))
gettext.bindtextdomain(DOMAIN, str(LOCALE_DIR))
_ = gettext.translation(DOMAIN, str(LOCALE_DIR), fallback=True).gettext


def set_ui_direction():
    from gi.repository import GLib, Gtk

    language = GLib.get_language_names()[0].split("_")[0].split("-")[0]
    Gtk.Widget.set_default_direction(
        Gtk.TextDirection.RTL if language in {"ar", "ur"} else Gtk.TextDirection.LTR
    )

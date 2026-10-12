# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check desktop selection independently of installed desktop environments."""

import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from desktop_backend import select
import desktop_manage


class DesktopBackendTests(unittest.TestCase):
    def test_owned_legacy_launcher_migrates_without_touching_custom_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "applications/io.github.hawkab.UbuntuDockFolders.desktop"
            path.parent.mkdir()
            with patch.object(desktop_manage.GLib, "get_user_data_dir", return_value=directory):
                path.write_text("[Desktop Entry]\nName=My custom label\nExec=/usr/bin/python3 /usr/share/gnome-shell/extensions/dock-groups@local/app/preferences.py --global\n")
                desktop_manage.migrate_launcher()
                self.assertIn("Exec=ubuntu-dock-folders preferences", path.read_text())
                self.assertIn("Name=My custom label", path.read_text())
                path.write_text("[Desktop Entry]\nExec=my-custom-command\n")
                desktop_manage.migrate_launcher()
                self.assertIn("Exec=my-custom-command", path.read_text())

    def test_previously_initialized_desktop_is_not_reenabled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "launcher-groups/desktop-sessions.json"
            path.parent.mkdir()
            path.write_text('["xfce"]')
            with patch.object(desktop_manage.GLib, "get_user_data_dir", return_value=directory), \
                    patch.object(desktop_manage, "dispatch") as dispatch:
                self.assertEqual(desktop_manage.session(select({
                    "XDG_CURRENT_DESKTOP":"XFCE","XDG_SESSION_TYPE":"wayland"})),0)
                dispatch.assert_not_called()

    def test_plasma_refreshes_catalogs_without_reenabling_a_visited_desktop(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"launcher-groups/desktop-sessions.json"
            path.parent.mkdir()
            path.write_text('["plasma"]')
            with patch.object(desktop_manage.GLib,"get_user_data_dir",return_value=directory), \
                    patch.object(desktop_manage,"sync_plasma_locales") as refresh, \
                    patch.object(desktop_manage,"dispatch") as dispatch:
                self.assertEqual(desktop_manage.session(select({
                    "XDG_CURRENT_DESKTOP":"KDE","XDG_SESSION_TYPE":"wayland"})),0)
                refresh.assert_called_once_with()
                dispatch.assert_not_called()
    def test_selects_all_desktops_on_both_session_types(self):
        for desktop, expected in (("ubuntu:GNOME", "gnome"), ("KDE", "plasma"), ("XFCE", "xfce")):
            for session in ("x11", "wayland"):
                with self.subTest(desktop=desktop, session=session):
                    self.assertEqual(select({"XDG_CURRENT_DESKTOP": desktop, "XDG_SESSION_TYPE": session}).name,
                                     expected + "-" + session)

    def test_wayland_takes_precedence_over_xwayland_display(self):
        self.assertEqual(select({"XDG_CURRENT_DESKTOP": "XFCE", "DISPLAY": ":0",
                                 "WAYLAND_DISPLAY": "wayland-0"}).name, "xfce-wayland")

    def test_rejects_unknown_desktop_and_non_graphical_session(self):
        for environment in ({}, {"XDG_CURRENT_DESKTOP": "sway", "XDG_SESSION_TYPE": "wayland"}):
            with self.assertRaises(RuntimeError):
                select(environment)

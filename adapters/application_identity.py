# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Read launcher arguments for the portable PWA identity index."""

from gi.repository import GLib


def pwa_entries(infos):
    """Return Chrome launchers and parsed arguments without executing commands."""
    entries = []
    for info in infos:
        desktop = info.get_id() or ""
        if not desktop.startswith("chrome-") or not desktop.endswith(".desktop"):
            continue
        try:
            _ok, argv = GLib.shell_parse_argv(info.get_commandline() or "")
        except GLib.Error:
            argv = []
        entries.append({"desktop": desktop, "argv": argv})
    return entries

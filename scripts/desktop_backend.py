# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Select a desktop adapter without binding an installation to one session type."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Backend:
    desktop: str
    session: str

    @property
    def name(self):
        return self.desktop + "-" + self.session


def select(environment=None):
    """Return the declared desktop and display backend; reject unsupported sessions."""
    environment = os.environ if environment is None else environment
    desktops = environment.get("XDG_CURRENT_DESKTOP", "").lower().split(":")
    session = environment.get("XDG_SESSION_TYPE", "").lower()
    if session not in ("wayland", "x11"):
        session = "wayland" if environment.get("WAYLAND_DISPLAY") else "x11" if environment.get("DISPLAY") else ""
    if session not in ("wayland", "x11"):
        raise RuntimeError("Run this command in a graphical desktop session.")
    for desktop in desktops:
        if desktop in ("xfce", "x-xfce"):
            return Backend("xfce", session)
        if desktop in ("kde", "plasma"):
            return Backend("plasma", session)
        if desktop in ("gnome", "ubuntu"):
            return Backend("gnome", session)
    raise RuntimeError("Supported desktops: GNOME, KDE Plasma and Xfce.")


def preferences_path(desktop, prefix=Path("/usr/share")):
    if desktop == "xfce":
        return prefix / "ubuntu-dock-folders/xfce/shared/app/preferences.py"
    if desktop == "gnome":
        return prefix / "gnome-shell/extensions/dock-groups@local/app/preferences.py"
    raise ValueError("Plasma preferences use the native widget configuration interface.")

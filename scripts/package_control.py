# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Read and update Debian package fields without altering unrelated metadata."""

from debian.deb822 import Deb822


DESCRIPTION = (
    " Group applications by dragging one dock icon onto another. Reorder them\n"
    " inside folders or move them back to the dock. Each folder shows real\n"
    " application icons and a shared running indicator.\n .\n"
    " Customize names, labels, colors, transparency and wallpaper. Choose among\n"
    " eight animations and adjust each folder background blur. The interface follows\n"
    " the system language and includes 30 translations.\n .\n"
)


def description(desktops=False):
    if desktops:
        title = "Application folders for GNOME, KDE Plasma and Xfce\n"
        setup = (
            " Selects the desktop adapter automatically at login. Switching between\n"
            " supported X11 and Wayland sessions does not require reinstalling.\n"
        )
    else:
        title = "Android-style application folders for Ubuntu Dock\n"
        setup = (
            " Supports Ubuntu 26.04 / GNOME 50 and Ubuntu 24.04 / GNOME 46 with Ubuntu Dock.\n"
            " Run ubuntu-dock-folders enable --ubuntu-settings as your desktop user,\n"
            " then log out and back in.\n"
        )
    return title + DESCRIPTION + setup + " .\n Author: Grigory Olshansky. License: GPL-3.0-or-later."


def update(path, fields):
    control = Deb822(path.read_text())
    control.update(fields)
    path.write_text(control.dump())


def combined(path, version, dependencies):
    update(path, {
        "Version": version,
        "Depends": dependencies,
        "Section": "x11",
        "Replaces": "ubuntu-dock-folders-xfce, ubuntu-dock-folders-kwin, ubuntu-dock-folders-kwin-x11",
        "Conflicts": "ubuntu-dock-folders-kwin, ubuntu-dock-folders-kwin-x11",
        "Provides": "ubuntu-dock-folders-xfce, ubuntu-dock-folders-kwin, ubuntu-dock-folders-kwin-x11",
        "Suggests": "gnome-shell-extension-ubuntu-dock, plasma-workspace, xfce4-panel",
        "Description": description(desktops=True),
    })

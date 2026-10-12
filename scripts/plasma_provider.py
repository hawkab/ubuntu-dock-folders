# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Select a Plasma package provider without letting user copies mask APT updates."""

import shutil
import subprocess
from pathlib import Path

from plasma_removal import remove_locales

ID = "io.github.hawkab.DockFolders"
SYSTEM_PACKAGE = Path("/usr/share/plasma/plasmoids") / ID


def source(root):
    """Prefer a repository build; installed management commands use the system widget."""
    built = root / "build/plasma"
    package = built if built.is_dir() else SYSTEM_PACKAGE
    if not package.is_dir():
        raise RuntimeError("Build the widget first: make build-plasma")
    return package


def owned_override(state, service, installed):
    """Identify user copies created by this installer, retaining arbitrary dev copies."""
    return state.exists() or (service.is_file() and
        f"Name={ID}.Plasma\n" in service.read_text() and
        str(installed / "contents/code/service.py") in service.read_text())


def install(package, installed, saved, data, owned):
    """Activate a system provider or install a local review build; back up owned overrides."""
    if package == SYSTEM_PACKAGE:
        if installed.exists():
            if not owned:
                raise RuntimeError("A user-installed Dock Folders widget shadows the system package. "
                                   "Back up or remove that widget before enabling the package.")
            shutil.copytree(installed, saved / "plasma-widget", symlinks=True)
            remove_locales(installed, data)
            shutil.rmtree(installed)
        return package
    action = "--upgrade" if installed.exists() else "--install"
    subprocess.run(["kpackagetool6", "--type", "Plasma/Applet", action, str(package)], check=True)
    return installed

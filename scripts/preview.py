#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Open an offline AppStream preview in GNOME Software."""

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from gi.repository import GLib

ROOT = Path(__file__).resolve().parent.parent
APP_ID = "io.github.hawkab.UbuntuDockFolders"


def main():
    if not shutil.which("gnome-software"):
        raise SystemExit("Install gnome-software to view the AppStream preview.")
    source = ROOT / "build/package/usr/share/metainfo" / f"{APP_ID}.metainfo.xml"
    if not source.exists():
        raise SystemExit("Build the package first: make build")
    cache = Path(GLib.get_user_cache_dir()) / "ubuntu-dock-folders"
    cache.mkdir(parents=True, exist_ok=True)
    icon = cache / "icon.png"
    shutil.copy2(
        ROOT / "build/package/usr/share/icons/hicolor/128x128/apps" / f"{APP_ID}.png", icon
    )
    tree = ET.parse(source)
    component = tree.getroot()
    for stock in component.findall("icon"):
        component.remove(stock)
    for media in component.findall("screenshots/screenshot/image") + component.findall(
        "screenshots/screenshot/video"
    ):
        filename = media.text.rsplit("/", 1)[-1]
        destination = cache / filename
        shutil.copy2(ROOT / "docs" / filename, destination)
        media.text = destination.as_uri()
    ET.SubElement(component, "icon", {"type": "local"}).text = str(icon)
    destination = cache / "preview.metainfo.xml"
    tree.write(destination, encoding="UTF-8", xml_declaration=True)
    subprocess.Popen(["gnome-software", "--show-metainfo", f"{destination},icon={icon}"])


if __name__ == "__main__":
    main()

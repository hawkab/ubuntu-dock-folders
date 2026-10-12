# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Add desktop-specific screenshots to the combined package's AppStream catalogs."""

from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "https://raw.githubusercontent.com/hawkab/ubuntu-dock-folders/main/docs/"
DOCUMENTATION = Path("/usr/share/doc/ubuntu-dock-folders/docs")
SCREENS = (
    ("general-settings.png", "Dock icons and hover effects"),
    ("general-settings-open.png", "Application size and opening animations"),
    ("existing-folders.png", "Existing application folders"),
    ("folder-settings-dock.png", "Folder appearance on the panel"),
    ("folder-settings-open.png", "Open folder background and blur"),
)


def extend(component, local=False, root=ROOT):
    """Append five screenshots per desktop, using public or packaged URLs."""
    screenshots = component.find("screenshots")
    for desktop, name in (("plasma", "KDE Plasma"), ("xfce", "Xfce")):
        for filename, caption in SCREENS:
            relative = desktop + "/" + filename
            with Image.open(root / "docs" / relative) as image:
                width, height = image.size
            screenshot = ET.SubElement(screenshots, "screenshot")
            ET.SubElement(screenshot, "caption").text = name + ": " + caption
            ET.SubElement(screenshot, "image", {"type": "source", "width": str(width),
                                               "height": str(height)}).text = (
                (DOCUMENTATION / relative).as_uri() if local else PUBLIC + relative)

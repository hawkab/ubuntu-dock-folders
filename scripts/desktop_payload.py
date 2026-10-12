# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Stage desktop providers, session dispatch and their AppStream media."""

import json
import re
import shutil
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from desktop_catalog import extend as add_desktop_screenshots

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from adapters.dependency import verify_core

PLASMA_ID = "io.github.hawkab.DockFolders"
FRONTENDS = ("build/extension", "build/plasma/contents", "build/xfce/shared")


def verify_builds(root=ROOT):
    """Reject missing, corrupt or stale provider cores before changing the stage."""
    canonical = verify_core(root)
    for frontend in FRONTENDS:
        if verify_core(root / frontend) != canonical:
            raise RuntimeError("Rebuild all desktop adapters against the current core.")
    return canonical["api"]


def install_plasma(stage, root=ROOT):
    widget = stage / "usr/share/plasma/plasmoids" / PLASMA_ID
    shutil.copytree(root / "build/plasma", widget,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    management = stage / "usr/share/ubuntu-dock-folders/plasma-management"
    management.mkdir()
    for name in ("plasma_manage.py", "plasma_recovery.py", "plasma_update.py", "plasma_removal.py",
                 "plasma_provider.py", "plasma_package_lifecycle.py", "backup.py", "install_context.py"):
        shutil.copy2(root / "scripts" / name, management / name)


def install_dispatcher(stage, root=ROOT):
    scripts = stage / "usr/share/ubuntu-dock-folders/scripts"
    for name in ("desktop_backend.py", "desktop_manage.py", "desktop_package_lifecycle.py"):
        shutil.copy2(root / "scripts" / name, scripts / name)
    executable = stage / "usr/bin/ubuntu-dock-folders"
    executable.write_text('#!/usr/bin/python3\nimport runpy,sys\n'
        'sys.path.insert(0,"/usr/share/ubuntu-dock-folders/scripts")\n'
        'runpy.run_path("/usr/share/ubuntu-dock-folders/scripts/desktop_manage.py",run_name="__main__")\n')
    executable.chmod(0o755)
    desktop = stage / "usr/share/applications/io.github.hawkab.UbuntuDockFolders.desktop"
    text = re.sub(r"^Exec=.*$", "Exec=ubuntu-dock-folders preferences", desktop.read_text(), flags=re.M)
    desktop.write_text(re.sub(r"^Categories=.*$", "Categories=Settings;DesktopSettings;", text, flags=re.M))
    autostart = stage / "etc/xdg/autostart/ubuntu-dock-folders.desktop"
    autostart.parent.mkdir(parents=True)
    autostart.write_text("[Desktop Entry]\nType=Application\nName=Ubuntu Dock Folders\n"
        "Exec=ubuntu-dock-folders session\nOnlyShowIn=GNOME;KDE;XFCE;\n"
        "X-GNOME-Autostart-Phase=Applications\nNoDisplay=true\n")
    (stage / "usr/share/ubuntu-dock-folders/desktops.json").write_text(json.dumps({
        "desktops": ["gnome", "plasma", "xfce"], "sessions": ["x11", "wayland"]}) + "\n")
    control = stage / "DEBIAN"
    (control / "conffiles").write_text("/etc/xdg/autostart/ubuntu-dock-folders.desktop\n")


def update_catalogs(stage):
    for source in (stage / "usr/share/metainfo", stage / "usr/share/swcatalog/xml"):
        for file in source.glob("*.xml"):
            tree = ET.parse(file)
            component = tree.getroot()
            if component.tag == "components":
                component = component.find("component")
            for paragraph in component.findall("description/p"):
                if (paragraph.get("{http://www.w3.org/XML/1998/namespace}lang") is None
                        and (paragraph.text or "").startswith("Designed for")):
                    paragraph.text = (
                        "Application folders for GNOME with Ubuntu Dock, KDE Plasma 6.6 or newer, "
                        "and Xfce 4.20. The desktop and display backend are selected automatically when you "
                        "log in. X11 and Wayland sessions share the same folder settings.")
            add_desktop_screenshots(component, local=source.name == "xml")
            ET.indent(tree, space="  ")
            tree.write(file, encoding="UTF-8", xml_declaration=True)

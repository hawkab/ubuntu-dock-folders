# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Keep catalog metadata readable by Ubuntu 24.04 software centers."""

import copy
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET


def add_legacy_developer(component):
    developer = component.find("developer")
    if developer is None:
        return
    for name in developer.findall("name"):
        legacy = copy.deepcopy(name)
        legacy.tag = "developer_name"
        component.append(legacy)


def verify_local_media(package):
    with tempfile.TemporaryDirectory(prefix="dock-folders-media-") as directory:
        root = Path(directory)
        subprocess.run(["dpkg-deb", "--extract", str(package), str(root)], check=True)
        catalogs = list((root / "usr/share/swcatalog/xml").glob("*.xml"))
        if not catalogs:
            raise ValueError("Package has no local AppStream catalog")
        for catalog in catalogs:
            tree = ET.parse(catalog)
            resources = tree.findall(".//screenshots/screenshot/image")
            resources += tree.findall(".//screenshots/screenshot/video")
            resources += tree.findall(".//icon[@type='local']")
            if not resources:
                raise ValueError("Package catalog has no local media")
            for resource in resources:
                url = urlparse(resource.text.strip())
                path = Path(unquote(url.path))
                local = url.scheme == "file" or (resource.tag == "icon" and not url.scheme)
                if not local or url.netloc or not path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"Invalid local media URL: {resource.text}")
                file = root / path.relative_to("/")
                if not file.resolve().is_relative_to(root) or not file.is_file():
                    raise ValueError(f"Package media is missing: {path}")

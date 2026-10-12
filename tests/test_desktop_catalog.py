# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify public and packaged media URLs for the combined desktop catalog."""

import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import desktop_catalog


class DesktopCatalogTests(unittest.TestCase):
    def test_combined_screenshots_keep_desktop_subdirectories(self):
        for local in (False, True):
            with self.subTest(local=local):
                component = ET.fromstring("<component><screenshots/></component>")
                desktop_catalog.extend(component, local=local)
                screenshots = component.findall("screenshots/screenshot")
                self.assertEqual(len(screenshots), 10)
                for screenshot in screenshots:
                    image = screenshot.find("image")
                    url = urlparse(image.text)
                    self.assertEqual(url.scheme, "file" if local else "https")
                    self.assertTrue("/plasma/" in url.path or "/xfce/" in url.path)
                    self.assertGreater(int(image.get("width")), 0)
                    self.assertGreater(int(image.get("height")), 0)

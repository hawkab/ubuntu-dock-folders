# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify offline package metadata and the extension bundle."""

import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "build/package"
APP_ID = "io.github.hawkab.UbuntuDockFolders"


class PackageTests(unittest.TestCase):
    def test_donation_uses_same_public_page_in_package_and_catalog(self):
        public = ET.parse(ROOT / "packaging" / f"{APP_ID}.metainfo.xml").getroot()
        link = public.findtext("url[@type='donation']")
        self.assertEqual(link, "https://hawkab.github.io/support/")
        local = ET.parse(STAGE / "usr/share/swcatalog/xml" / f"{APP_ID}.xml").find("component")
        self.assertEqual(local.findtext("url[@type='donation']"), link)

    def test_local_catalog_resolves_packaged_media_without_network(self):
        catalog = STAGE / "usr/share/swcatalog/xml" / f"{APP_ID}.xml"
        component = ET.parse(catalog).getroot().find("component")
        self.assertEqual(component.findtext("pkgname"), "ubuntu-dock-folders")
        images = component.findall("screenshots/screenshot/image")
        videos = component.findall("screenshots/screenshot/video")
        self.assertEqual(len(images), 7)
        self.assertEqual(len(videos), 1)
        for media in images + videos:
            with self.subTest(url=media.text):
                url = urlparse(media.text)
                self.assertEqual(url.scheme, "file")
                self.assertFalse(url.netloc)
                path = Path(unquote(url.path))
                self.assertEqual(path.parent, Path("/usr/share/doc/ubuntu-dock-folders/docs"))
                self.assertTrue((STAGE / path.relative_to("/")).is_file())
        icon = component.find("icon[@type='local']")
        self.assertTrue((STAGE / Path(icon.text).relative_to("/")).is_file())

    def test_extension_bundle_contains_hover_preview_module(self):
        with zipfile.ZipFile(ROOT / "dist/dock-groups@local.shell-extension.zip") as bundle:
            self.assertIn("windowPreviews.js", bundle.namelist())
            self.assertIn("./windowPreviews.js", bundle.read("extension.js").decode())


if __name__ == "__main__":
    unittest.main()

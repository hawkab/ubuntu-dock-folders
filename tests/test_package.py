# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify offline package metadata and the extension bundle."""

import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "build/package"
APP_ID = "io.github.hawkab.UbuntuDockFolders"
sys.path.insert(0, str(ROOT / "scripts"))
import apt_repo


class PackageTests(unittest.TestCase):
    """Check installed and repository catalogs against supported store formats."""

    def test_local_catalog_supports_confined_and_legacy_readers(self):
        component = ET.parse(STAGE / "usr/share/swcatalog/xml" / f"{APP_ID}.xml").find("component")
        self.assertEqual(component.findtext("developer_name"), component.findtext("developer/name"))
        self.assertEqual(
            component.findtext("developer_name[@{http://www.w3.org/XML/1998/namespace}lang='ru']"),
            "Григорий Ольшанский",
        )
        self.assertEqual(component.findtext("icon[@type='stock']"), APP_ID)
        self.assertEqual(
            component.findtext("icon[@type='remote']"),
            f"https://hawkab.github.io/apt/icons/{APP_ID}.png",
        )
        self.assertIn("ubuntu-dock-folders", [item.text for item in component.findall("keywords/keyword")])

    def test_repository_catalog_has_downloadable_icon_and_legacy_author(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            output = archive / "dists/noble/main/dep11"
            output.mkdir(parents=True)
            package = archive / "catalog-test.deb"
            subprocess.run(
                ["dpkg-deb", "--build", "--root-owner-group", STAGE, package],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            apt_repo.compose(
                package,
                output,
                {"suite": "noble", "architecture": "amd64"},
            )
            metadata = (output / "Components-amd64.yml").read_text()
            self.assertTrue(metadata.startswith("---\nFile: DEP-11\n"))
            _, component = list(yaml.safe_load_all(metadata))
            self.assertEqual(component["DeveloperName"], component["Developer"]["name"])
            remote = component["Icon"]["remote"][0]["url"]
            self.assertEqual(remote, f"https://hawkab.github.io/apt/icons/{APP_ID}.png")
            self.assertTrue((archive / "icons" / f"{APP_ID}.png").is_file())
            self.assertTrue(component["Icon"]["cached"])
            self.assertIn("ubuntu-dock-folders", component["Keywords"]["C"])
            self.assertIn("Settings", component["Categories"])

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

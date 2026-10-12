# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify clean-install defaults, existing settings and core bundle compatibility."""

import json
import tempfile
import shutil
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from gi.repository import Gio, GLib
from adapters.runtime import CoreRuntime
from adapters.dependency import verify_core
from backend_build import frontend

ROOT = Path(__file__).resolve().parent.parent


class DefaultTests(unittest.TestCase):
    def setUp(self):
        self.core = CoreRuntime(ROOT)
        self.addCleanup(self.core.close)

    def test_new_folders_use_the_profile_without_private_data(self):
        entries = {id:{"desktop":id,"label":id} for id in ("a","b")}
        for command in ({"operation":"create","desktop":"a","target":"b","name":"New"},
                        {"operation":"importFolder","apps":["a","b"],"name":"New","gridFolder":"Utilities"}):
            result = self.core.call("transaction",{"state":{"groups":{},"favorites":["a","b"]},
                "entries":entries,"token":"defaults","command":command})
            self.assertTrue(result["changed"])
            folder = result["state"]["groups"]["folder-defaults"]
            value = self.core.call("surface",{"group":folder})
            self.assertEqual((value["dockColor"],value["dockOpacity"]),("#787878",.1))
            self.assertEqual((value["backgroundOpacity"],value["blurStrength"]),(.26,89))
            self.assertEqual((value["iconRotation"],value["alwaysStack"]),(0,False))
            self.assertFalse(value["showLabel"])
            self.assertEqual(folder["wallpaper"],"")
            self.assertNotIn("wallpaperFolder",folder)
            self.assertEqual(folder["name"],"New")

    def test_gsettings_and_kconfig_have_the_same_clean_defaults(self):
        contract = self.core.call("contract")
        expected = {"animation":"flow","animationSpeed":180,"groupIconSize":120,
                    "groupMiniIconSize":230,"popupIconSize":56,"fontSize":13,
                    "hoverAngle":45,"hoverSpeed":50,"blurStrength":89,"orbitSpeed":0,"hoverOrbitSpeed":0}
        source = Gio.SettingsSchemaSource.new_from_directory(str(ROOT/"build/extension/schemas"),Gio.SettingsSchemaSource.get_default(),False)
        schema = source.lookup("org.gnome.shell.extensions.dock-groups",False)
        self.assertIsNotNone(schema)
        entries = {node.attrib["name"]:node for node in ET.parse(ROOT/"plasma/contents/config/main.xml").getroot().find("{*}group")}
        for descriptor in contract["preferences"]:
            name = descriptor["name"]
            if name not in expected:
                continue
            self.assertEqual(schema.get_key(descriptor["key"]).get_default_value().unpack(),expected[name])
            default = entries[name].find("{*}default").text
            self.assertEqual(float(default),1 if name == "animation" else expected[name])
        self.assertEqual(entries["fontSize"].attrib["type"],"Double")
        blur = schema.get_key("blur-strength")
        self.assertTrue(blur.range_check(GLib.Variant("i", -1)))
        self.assertEqual(self.core.call("preferences", {"blurStrength": -1})["blurStrength"], 100)

    def test_updates_keep_explicit_and_legacy_appearance(self):
        old = {"id":"local.groups.Old","dockOpacity":.67,"popupOpacity":.91,"glassOpacity":.38,
               "popupColor":"#ffffff","blurStrength":25,"showLabel":False}
        value = self.core.call("surface",{"group":old,"blurStrength":89})
        self.assertEqual((value["dockOpacity"],value["backgroundOpacity"],value["blurStrength"]),(.67,.38,25))
        self.assertFalse(value["showLabel"])
        bare = self.core.call("surface",{"group":{"id":"local.groups.Legacy"},"blurStrength":-1})
        self.assertEqual((bare["backgroundOpacity"],bare["blurStrength"]),(.42,100))
        self.assertEqual(self.core.call("preferences",{"animation":"none","groupIconSize":95})["groupIconSize"],95)

    def test_all_frontends_require_identical_core_files(self):
        expected = verify_core(ROOT)
        for desktop in ("gnome", "plasma", "xfce"):
            with self.subTest(desktop=desktop):
                self.assertEqual(verify_core(frontend(self, desktop)), expected)
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)
            shutil.copytree(ROOT/"core",target/"core")
            (target/"core/preferences.js").write_text("incompatible")
            with self.assertRaises(RuntimeError):
                verify_core(target)

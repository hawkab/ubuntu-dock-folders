# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check Xfce removal while preserving unrelated panel slots and folder settings."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from gi.repository import GLib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import xfce_manage


class XfceInstallTests(unittest.TestCase):
    def test_wayland_reuses_existing_panel_slot_without_changing_settings(self):
        with patch.dict(xfce_manage.os.environ, {"XDG_SESSION_TYPE": "wayland"}), \
                patch.object(xfce_manage, "properties", return_value={
                    "/plugins/plugin-23": GLib.Variant("s", "dockfolders")}), \
                patch.object(xfce_manage, "set_property") as write:
            xfce_manage.enable(Path("/unused"))
            write.assert_not_called()

    def test_explicit_dock_panel_does_not_replace_another_panels_tasklist(self):
        values = {"/panels/panel-1/plugin-ids": GLib.Variant("av", [GLib.Variant("i", 2)]),
                  "/panels/panel-2/plugin-ids": GLib.Variant("av", [GLib.Variant("i", 3)]),
                  "/plugins/plugin-2": GLib.Variant("s", "tasklist"),
                  "/plugins/plugin-3": GLib.Variant("s", "launcher")}
        key, original, replaced = xfce_manage.panel_slot(values, 2)
        self.assertEqual((key, original.unpack(), replaced), ("/panels/panel-2/plugin-ids", [3], None))
        self.assertEqual(xfce_manage.panel_slot(values)[2], 2)
        with self.assertRaises(RuntimeError):
            xfce_manage.panel_slot(values, 99)

    def test_offline_removal_restores_only_our_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            state.write_text(json.dumps({"plugin": 30, "replaced": 4}))
            file = root / "xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
            file.parent.mkdir(parents=True)
            file.write_text('<channel name="xfce4-panel"><property name="panels"><property name="panel-1"><property name="plugin-ids" type="array"><value type="int" value="3"/><value type="int" value="30"/><value type="int" value="7"/></property></property></property><property name="plugins"><property name="plugin-30" type="string" value="dockfolders"/><property name="plugin-4" type="string" value="tasklist"/><property name="plugin-7" type="string" value="clock"/></property></channel>')
            with patch.object(xfce_manage, "STATE", state), patch.object(xfce_manage.GLib, "get_user_config_dir", return_value=directory):
                xfce_manage.disable_offline()
                xml = ET.parse(file)
                self.assertEqual([value.get("value") for value in xml.findall('.//value')], ["3", "4", "7"])
                self.assertIsNotNone(xml.find("./property[@name='plugins']/property[@name='plugin-7']"))
                self.assertIsNone(xml.find("./property[@name='plugins']/property[@name='plugin-30']"))
                self.assertFalse(state.exists())
                before = file.read_bytes()
                xfce_manage.disable_offline()
                self.assertEqual(before, file.read_bytes())

    def test_changed_plugin_identity_is_not_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            state.write_text(json.dumps({"plugin": 30, "replaced": 4}))
            file = root / "xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
            file.parent.mkdir(parents=True)
            file.write_text('<channel><property name="plugins"><property name="plugin-30" value="clock"/></property></channel>')
            before = file.read_bytes()
            with patch.object(xfce_manage, "STATE", state), patch.object(xfce_manage.GLib, "get_user_config_dir", return_value=directory):
                xfce_manage.disable_offline()
            self.assertEqual(file.read_bytes(), before)

    def test_manual_offline_plugin_is_removed_without_install_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
            file.parent.mkdir(parents=True)
            file.write_text('<channel><property name="panels"><property name="panel-1"><property name="plugin-ids"><value type="int" value="8"/><value type="int" value="9"/></property></property></property><property name="plugins"><property name="plugin-8" value="dockfolders"/><property name="plugin-9" value="clock"/></property></channel>')
            with patch.object(xfce_manage, "STATE", root / "missing-state.json"), patch.object(xfce_manage.GLib, "get_user_config_dir", return_value=directory):
                xfce_manage.disable_offline()
            xml = ET.parse(file)
            self.assertEqual([value.get("value") for value in xml.findall('.//value')], ["9"])
            self.assertIsNotNone(xml.find("./property[@name='plugins']/property[@name='plugin-9']"))

    def test_live_removal_preserves_repurposed_ids_and_restores_tasklist(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(json.dumps({"plugin": 30, "replaced": 4}))
            values = {"/panels/panel-1/plugin-ids": GLib.Variant("av", [GLib.Variant("i", n) for n in (3, 30, 7, 40)]),
                      "/plugins/plugin-3": GLib.Variant("s", "separator"),
                      "/plugins/plugin-4": GLib.Variant("s", "tasklist"),
                      "/plugins/plugin-7": GLib.Variant("s", "clock"),
                      "/plugins/plugin-30": GLib.Variant("s", "dockfolders"),
                      "/plugins/plugin-40": GLib.Variant("s", "dockfolders")}
            with patch.object(xfce_manage, "STATE", state), patch.object(xfce_manage, "properties", return_value=values), patch.object(xfce_manage, "set_property") as save, patch.object(xfce_manage, "call") as reset:
                xfce_manage.disable(restart=False)
                self.assertEqual(save.call_args.args[1].unpack(), [3, 4, 7])
                self.assertEqual({call.args[1].unpack()[1] for call in reset.call_args_list}, {"/plugins/plugin-30", "/plugins/plugin-40"})
                state.write_text(json.dumps({"plugin": 30, "replaced": 4}))
                values["/plugins/plugin-30"] = GLib.Variant("s", "clock")
                del values["/plugins/plugin-40"]
                save.reset_mock()
                reset.reset_mock()
                xfce_manage.disable(restart=False)
                save.assert_not_called()
                reset.assert_not_called()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify removal of managed and manually added Plasma widgets."""

import json
import mmap
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_manage
import plasma_removal
from plasma_recovery import recover


class PlasmaRemovalTests(unittest.TestCase):
    def test_active_widgets_are_removed_without_install_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "missing.json"
            connection = Mock()
            connection.call_sync.return_value.unpack.return_value = (True,)
            manager = SimpleNamespace(
                Gio=plasma_manage.Gio, GLib=plasma_manage.GLib, ID=plasma_manage.ID, STATE=state,
                snapshot=lambda: [{"id": 2, "height": 46, "widgets": [
                    {"id": 7, "type": "org.kde.plasma.systemtray"},
                    {"id": 29, "type": plasma_manage.ID}, {"id": 30, "type": plasma_manage.ID}]}],
                evaluate=Mock(), place_widget=Mock(),
            )
            with patch.object(plasma_removal.os, "geteuid", return_value=1000), patch.object(
                    plasma_manage.Gio, "bus_get_sync", return_value=connection):
                plasma_removal.disable(manager)
            scripts = [call.args[0] for call in manager.evaluate.call_args_list]
            self.assertEqual(len(scripts), 2)
            self.assertIn("widgetById(29)", scripts[0])
            self.assertIn("widgetById(30)", scripts[1])
            self.assertTrue(all("widgetById(7)" not in script for script in scripts))
            manager.place_widget.assert_not_called()

    def test_offline_removal_preserves_other_widgets_and_changed_panel_height(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, state = root / "panel", root / "missing.json"
            text = "[Containments][2]\nformfactor=2\n\n"
            text += "[Containments][2][Applets][7]\nplugin=org.kde.plasma.systemtray\n\n"
            text += "[Containments][2][Applets][29]\nplugin=io.github.hawkab.DockFolders\n\n"
            text += "[Containments][2][Applets][29][Configuration][General]\nhoverSpeed=999\n\n"
            text += "[Containments][2][General]\nAppletOrder=3;4;29;7;18\nheight=60\n"
            config.write_text(text)
            config.chmod(0o600)
            self.assertTrue(recover(config, state))
            result = config.read_text()
            self.assertIn("AppletOrder=3;4;7;18", result)
            self.assertIn("plugin=org.kde.plasma.systemtray", result)
            self.assertIn("height=60", result)
            self.assertNotIn("[Applets][29]", result)
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            self.assertFalse(recover(config, state))

    def test_corrupt_state_does_not_block_owned_widget_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, state = root / "panel", root / "state.json"
            config.write_text("[Containments][2][Applets][29]\nplugin=io.github.hawkab.DockFolders\n")
            state.write_text("{truncated")
            self.assertTrue(recover(config, state))
            self.assertEqual(config.read_text(), "")
            self.assertFalse(state.exists())
            self.assertEqual(next(root.glob("state.invalid-*.json")).read_text(), "{truncated")

    def test_removed_managed_widget_does_not_restore_an_extra_task_manager(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, state = root / "panel", root / "state.json"
            text = "[Containments][2][Applets][7]\nplugin=org.kde.plasma.systemtray\n"
            config.write_text(text)
            state.write_text(json.dumps({"panel": 2, "widget": 29, "original": {
                "id": 26, "type": "org.kde.plasma.icontasks", "configuration": []}}))
            self.assertTrue(recover(config, state))
            self.assertEqual(config.read_text(), text)

    def test_stale_state_does_not_remove_a_reassigned_widget_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, state = root / "panel", root / "state.json"
            text = "[Containments][2][Applets][29]\nplugin=org.kde.plasma.digitalclock\n"
            config.write_text(text)
            state.write_text(json.dumps({"panel": 2, "widget": 29, "original": {
                "id": 26, "type": "org.kde.plasma.icontasks", "configuration": []}}))
            self.assertTrue(recover(config, state))
            self.assertEqual(config.read_text(), text)

    def test_locale_removal_keeps_changed_catalogs_and_mapped_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "widget/contents/locale/ru/LC_MESSAGES/ubuntu-dock-folders.mo"
            target = root / "data/locale/ru/LC_MESSAGES/ubuntu-dock-folders.mo"
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            source.write_bytes(b"owned catalog")
            target.write_bytes(b"owned catalog")
            unrelated = target.with_name("other-app.mo")
            unrelated.write_bytes(b"other app")
            with target.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                plasma_removal.remove_locales(root / "widget", root / "data")
                self.assertEqual(mapped[:], b"owned catalog")
            self.assertFalse(target.exists())
            self.assertEqual(unrelated.read_bytes(), b"other app")
            target.write_bytes(b"user catalog")
            plasma_removal.remove_locales(root / "widget", root / "data")
            self.assertEqual(target.read_bytes(), b"user catalog")

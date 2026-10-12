# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify system-provider upgrades without altering a real Plasma panel."""

import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_manage
import plasma_provider
import plasma_update


class PlasmaProviderTests(unittest.TestCase):
    def test_new_system_install_does_not_copy_a_user_widget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "data/plasma/plasmoids" / plasma_provider.ID
            provider = plasma_provider.install(plasma_provider.SYSTEM_PACKAGE, installed,
                                               root / "backup", root / "data", False)
            self.assertEqual(provider, plasma_provider.SYSTEM_PACKAGE)
            self.assertFalse(installed.exists())

    def test_system_install_retains_an_unowned_development_widget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "data/plasma/plasmoids" / plasma_provider.ID
            installed.mkdir(parents=True)
            (installed / "metadata.json").write_text("development widget")
            with self.assertRaisesRegex(RuntimeError, "user-installed.*shadows"):
                plasma_provider.install(plasma_provider.SYSTEM_PACKAGE, installed,
                                        root / "backup", root / "data", False)
            self.assertEqual((installed / "metadata.json").read_text(), "development widget")

    def test_owned_legacy_override_is_backed_up_before_using_system_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "data/plasma/plasmoids" / plasma_provider.ID
            installed.mkdir(parents=True)
            (installed / "metadata.json").write_text("previous installed widget")
            provider = plasma_provider.install(plasma_provider.SYSTEM_PACKAGE, installed,
                                               root / "backup", root / "data", True)
            self.assertEqual(provider, plasma_provider.SYSTEM_PACKAGE)
            self.assertFalse(installed.exists())
            self.assertEqual((root / "backup/plasma-widget/metadata.json").read_text(),
                             "previous installed widget")

    def test_explicit_update_removes_the_masking_copy_and_preserves_panel_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "data/plasma/plasmoids" / plasma_provider.ID
            installed.mkdir(parents=True)
            (installed / "metadata.json").write_text("old widget")
            saved = root / "backup"
            saved.mkdir()
            panel = {"id": 2, "order": "3;4;30;6", "height": 46}
            manager = SimpleNamespace(
                ROOT=root, DATA=root / "data", GLib=plasma_manage.GLib,
                package_path=lambda: plasma_provider.SYSTEM_PACKAGE,
                stop_helper=Mock(), write_service=Mock(), install_locales=Mock(),
                snapshot=lambda: [dict(panel)],
            )
            with patch.object(plasma_update.subprocess, "run") as run:
                plasma_update.refresh(manager, saved, panel, installed)
            self.assertFalse(installed.exists())
            self.assertEqual((saved / "plasma-widget/metadata.json").read_text(), "old widget")
            manager.write_service.assert_called_once_with(plasma_provider.SYSTEM_PACKAGE)
            manager.install_locales.assert_not_called()
            self.assertEqual(run.call_args_list[0].args[0], ["systemctl", "--user", "stop", plasma_update.UNIT])
            self.assertEqual(run.call_args_list[-1].args[0], ["systemctl", "--user", "start", plasma_update.UNIT])

    def test_system_migration_failure_restores_the_owned_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "data/plasma/plasmoids" / plasma_provider.ID
            installed.mkdir(parents=True)
            (installed / "metadata.json").write_text("old widget")
            saved = root / "backup"
            saved.mkdir()
            manager = SimpleNamespace(
                ROOT=root, DATA=root / "data", package_path=lambda: plasma_provider.SYSTEM_PACKAGE,
                stop_helper=Mock(), write_service=Mock(side_effect=[RuntimeError("Activation failed"), None]),
                install_locales=Mock(),
            )
            with patch.object(plasma_update.subprocess, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "Activation failed"):
                    plasma_update.refresh(manager, saved, {"id": 2}, installed)
            self.assertEqual((installed / "metadata.json").read_text(), "old widget")
            self.assertEqual(manager.write_service.call_args.args[0], installed)
            self.assertEqual(run.call_args_list[-1].args[0], ["systemctl", "--user", "start", plasma_update.UNIT])

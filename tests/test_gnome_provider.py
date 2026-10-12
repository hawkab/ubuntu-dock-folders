# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify explicit provider migration without touching a live GNOME session."""

import json
import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gnome_provider import select_system
import manage


class GnomeProviderTests(unittest.TestCase):
    def test_live_shell_migration_does_not_reload_cached_modules(self):
        settings = Mock()
        settings.get_string.return_value = "{}"
        settings.get_boolean.return_value = False
        shell = Mock()
        shell.get_strv.return_value = []
        with patch.object(manage.files, "shell_available", return_value=True), \
                patch.object(manage, "select_system", return_value=Path("/system/extension")), \
                patch.object(manage, "read_settings", return_value=settings), \
                patch.object(manage.Gio.Settings, "new", return_value=shell), \
                patch.object(manage, "compatibility_launchers"), \
                patch.object(manage, "install_presentation"), \
                patch.object(manage, "install_group_launchers"), \
                patch.object(manage, "set_extension_enabled") as activate:
            manage.enable(system=True)
        activate.assert_not_called()

    def context(self, root, owned):
        user, system, state = root / "user", root / "system", root / "state.json"
        user.mkdir()
        system.mkdir()
        for path in (user, system):
            (path / "metadata.json").write_text(json.dumps({"uuid": "dock-groups@local"}))
        (user / "extension.js").write_text("old user extension")
        if owned:
            state.write_text("{}")
        return SimpleNamespace(USER_EXTENSION=user, SYSTEM_EXTENSION=system, STATE=state,
                               UUID="dock-groups@local", state=lambda: {"presentation_backups": {"desktop": None}})

    def test_managed_override_moves_to_backup_and_system_provider_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self.context(root, owned=True)
            saved = root / "backup"
            saved.mkdir()
            backup = Mock(return_value=saved)
            self.assertEqual(select_system(context, backup), context.SYSTEM_EXTENSION)
            self.assertFalse(context.USER_EXTENSION.exists())
            self.assertEqual((saved / "gnome-user-extension/extension.js").read_text(), "old user extension")
            backup.assert_called_once_with(None, context.USER_EXTENSION)

    def test_unowned_development_extension_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.context(Path(directory), owned=False)
            backup = Mock()
            with self.assertRaisesRegex(RuntimeError, "user-installed.*shadows"):
                select_system(context, backup)
            self.assertEqual((context.USER_EXTENSION / "extension.js").read_text(), "old user extension")
            backup.assert_not_called()

    def test_missing_system_package_does_not_move_the_user_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.context(Path(directory), owned=True)
            (context.SYSTEM_EXTENSION / "metadata.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "Install.*Debian package"):
                select_system(context, Mock())
            self.assertTrue(context.USER_EXTENSION.exists())

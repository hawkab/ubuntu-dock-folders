# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise desktop-entry escaping and loaded-library updates."""

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import manage
import install_context
import settings_integration


class DesktopIntegrationTests(unittest.TestCase):
    def test_gnome_package_preferences_command_uses_the_native_entry_point(self):
        with patch.object(sys, "argv", ["ubuntu-dock-folders", "preferences"]), \
                patch.object(manage.os, "geteuid", return_value=1001), \
                patch.object(manage.subprocess, "run") as run:
            manage.main()
        run.assert_called_once_with(["gnome-extensions", "prefs", "dock-groups@local"], check=True)

    def test_settings_cleanup_handles_legacy_or_missing_install_state(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            applications = root / "applications"
            applications.mkdir()
            service = root / "dbus-1/services/org.gnome.Settings.service"
            service.parent.mkdir(parents=True)
            owned = "[Desktop Entry]\nExec=/usr/share/gnome-shell/extensions/dock-groups@local/integration/ubuntu-settings network\n"
            settings = applications / "org.gnome.Settings.desktop"
            network = applications / "gnome-network-panel.desktop"
            wifi = applications / "gnome-wifi-panel.desktop"
            custom = applications / "gnome-power-panel.desktop"
            untouched = "[Desktop Entry]\nExec=/usr/bin/gnome-control-center power\nName=My power settings\n"
            stock = "[Desktop Entry]\nExec=gnome-control-center network\n"
            for file in (settings, network, wifi, service):
                file.write_text(owned)
            custom.write_text(untouched)
            data = root / "launcher-groups"
            data.mkdir()
            state = data / "install-state.json"
            state.write_text(json.dumps({"desktop_backups": {
                str(network): stock, str(wifi): owned,
                str(custom): "older custom entry", str(applications / "absent-panel.desktop"): owned,
            }, "ubuntu_settings": True}))
            with (
                patch.object(install_context, "DATA", data),
                patch.object(install_context, "STATE", state),
                patch.object(install_context, "APPLICATIONS", applications),
                patch.object(install_context, "SERVICE", service),
                patch.object(install_context, "refresh_desktop_database"),
                patch.object(install_context, "reload_settings_service") as reload,
            ):
                manage.remove_integration()
                manage.remove_integration()
                self.assertFalse(settings.exists())
                self.assertFalse(service.exists())
                self.assertFalse(wifi.exists())
                self.assertEqual(network.read_text(), stock)
                self.assertEqual(custom.read_text(), untouched)
                self.assertFalse((applications / "absent-panel.desktop").exists())
                self.assertEqual(json.loads(state.read_text())["desktop_backups"], {})
                self.assertEqual(reload.call_count, 2)


    def test_old_launchers_migrate_to_a_persistent_settings_wrapper(self):
        import shutil

        if not shutil.which("gnome-control-center"):
            self.skipTest("GNOME Settings is not installed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "launcher-groups"
            applications = root / "applications"
            applications.mkdir()
            desktop = applications / "org.gnome.Settings.desktop"
            desktop.write_text("[Desktop Entry]\nExec=/usr/share/gnome-shell/extensions/dock-groups@local/integration/ubuntu-settings\n")
            extension = root / "extension"
            integration = extension / "integration"
            integration.mkdir(parents=True)
            (integration / "settings-integration.so").write_bytes(b"fixture")
            shutil.copy2(ROOT / "integration/ubuntu-settings", integration / "ubuntu-settings")
            service = root / "dbus-1/services/org.gnome.Settings.service"
            with (
                patch.object(install_context, "DATA", data),
                patch.object(install_context, "STATE", data / "install-state.json"),
                patch.object(install_context, "APPLICATIONS", applications),
                patch.object(install_context, "SERVICE", service),
                patch.object(install_context, "installed_extension", return_value=extension),
                patch.object(install_context, "refresh_desktop_database"),
                patch.object(install_context, "reload_settings_service"),
            ):
                manage.migrate_integration()
                self.assertTrue((data / "ubuntu-settings").is_file())
                self.assertIn(str(data / "ubuntu-settings"), desktop.read_text())
                self.assertNotIn("/gnome-shell/extensions/", desktop.read_text())
                self.assertIn(" --gapplication-service", service.read_text())
                inode = desktop.stat().st_ino
                manage.migrate_integration()
                self.assertEqual(desktop.stat().st_ino, inode)
                manage.remove_integration()
                self.assertFalse(desktop.exists())
                self.assertFalse(service.exists())
                self.assertFalse((data / "ubuntu-settings").exists())
                desktop.write_text("[Desktop Entry]\nExec=/usr/share/gnome-shell/extensions/dock-groups@local/integration/ubuntu-settings\n")
                (integration / "settings-integration.so").unlink()
                with patch.object(install_context, "SYSTEM_EXTENSION", root / "missing-system-extension"):
                    manage.migrate_integration()
                self.assertFalse(desktop.exists())


    def test_settings_launcher_falls_back_after_companion_removal(self):
        import os
        import shutil

        if not shutil.which("gnome-control-center"):
            self.skipTest("GNOME Settings is not installed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            companion = data / "gnome-shell/extensions" / install_context.UUID / "integration"
            companion.mkdir(parents=True)
            wrapper = data / "launcher-groups/ubuntu-settings"
            wrapper.parent.mkdir()
            wrapper.write_bytes((ROOT / "integration/ubuntu-settings").read_bytes())
            wrapper.chmod(0o755)
            shutil.rmtree(companion.parent)
            result = subprocess.run(
                [str(wrapper), "--version"],
                env=dict(os.environ, XDG_DATA_HOME=str(data)),
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("gnome-control-center", result.stdout.lower())
            self.assertNotIn("cannot be preloaded", result.stderr)


    def test_application_entry_is_removed_without_losing_existing_files(self):
        import os

        code = """
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import manage
import install_context
import settings_integration
desktop=install_context.APPLICATIONS/(install_context.APP_ID+'.desktop')
desktop.parent.mkdir(parents=True)
desktop.write_text('existing user launcher')
manage.install_presentation(Path(sys.argv[2]))
assert 'Exec=/usr/bin/python3' in desktop.read_text()
assert '--global' in desktop.read_text()
manage.remove_presentation()
assert desktop.read_text()=='existing user launcher'
print('OK')
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "/usr/bin/python3",
                    "-c",
                    code,
                    str(ROOT / "scripts"),
                    str(ROOT / "build/extension"),
                ],
                env=dict(os.environ, XDG_DATA_HOME=directory),
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            self.assertEqual(result.stdout.strip(), "OK")


    def test_mapped_library_survives_update_and_shutdown(self):
        library = ROOT / "build/integration/settings-integration.so"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "integration.so"
            target.write_bytes(library.read_bytes())
            code = """
import ctypes,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from manage import atomic_copy
ctypes.CDLL('libgtk-4.so.1', mode=ctypes.RTLD_GLOBAL)
ctypes.CDLL('libadwaita-1.so.0', mode=ctypes.RTLD_GLOBAL)
loaded=ctypes.CDLL(sys.argv[2])
target=Path(sys.argv[2])
inode=target.stat().st_ino
atomic_copy(Path(sys.argv[3]),target)
assert target.stat().st_ino!=inode
"""
            result = subprocess.run(
                ["/usr/bin/python3", "-c", code, str(ROOT / "scripts"), str(target), str(library)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

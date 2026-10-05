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


class InstallTests(unittest.TestCase):
    def test_running_extension_is_updated_without_hot_reload(self):
        class Settings:
            def get_strv(self, key):
                return [manage.UUID] if key == "enabled-extensions" else []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            extension = root / "installed"
            extension.mkdir()
            old = extension / "extension.js"
            old.write_text("old")
            inode = old.stat().st_ino
            bundle = root / "dist" / f"{manage.UUID}.shell-extension.zip"
            bundle.parent.mkdir()
            with zipfile.ZipFile(bundle, "w") as archive:
                archive.writestr("extension.js", "new")
                archive.write(
                    ROOT / "extension/schemas/org.gnome.shell.extensions.dock-groups.gschema.xml",
                    "schemas/org.gnome.shell.extensions.dock-groups.gschema.xml",
                )
            with (
                patch.object(manage, "ROOT", root),
                patch.object(manage, "USER_EXTENSION", extension),
                patch.object(manage, "backup", return_value=root / "backup"),
                patch.object(manage.Gio.Settings, "new", return_value=Settings()),
                patch.object(manage, "enable") as enable,
            ):
                manage.install()
                enable.assert_called_once_with(False, activate=False)
            self.assertEqual(old.read_text(), "new")
            self.assertNotEqual(old.stat().st_ino, inode)
            self.assertTrue((extension / "schemas/gschemas.compiled").exists())

    def test_application_entry_is_removed_without_losing_existing_files(self):
        import os

        code = """
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import manage
desktop=manage.APPLICATIONS/(manage.APP_ID+'.desktop')
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

    def test_enable_before_shell_discovers_the_extension(self):
        values = {"enabled-extensions": ["other"], "disabled-extensions": [manage.UUID]}

        class Settings:
            def get_strv(self, key):
                return values[key][:]

            def set_strv(self, key, value):
                values[key] = value[:]

        with patch.object(manage.subprocess, "run") as run:
            run.return_value.returncode = 1
            with patch.object(manage.Gio.Settings, "new", return_value=Settings()):
                self.assertFalse(manage.set_extension_enabled(True))
                self.assertEqual(values["enabled-extensions"], ["other", manage.UUID])
                self.assertEqual(values["disabled-extensions"], [])

    def test_enable_restores_group_launchers_before_pinning_them(self):
        import json

        from gi.repository import Gio

        group = {
            "id": "local.groups.Tools",
            "name": "Инструменты",
            "icon": "folder",
            "apps": [{"desktop": "org.gnome.TextEditor.desktop", "label": "Text Editor"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            applications = root / "applications"
            pinned = []

            class ShellSettings:
                def get_strv(self, key):
                    return ["org.gnome.TextEditor.desktop"]

                def set_strv(self, key, value):
                    desktop = applications / (group["id"] + ".desktop")
                    info = Gio.DesktopAppInfo.new_from_filename(str(desktop))
                    self_test.assertIsNotNone(info)
                    self_test.assertEqual(info.get_name(), group["name"])
                    self_test.assertIn(str(root / "system/app/launcher.py"), info.get_commandline())
                    self_test.assertEqual(info.get_action_name("App0"), "Text Editor")
                    pinned.extend(value)

            class FolderSettings:
                def get_string(self, key):
                    return json.dumps({"tools": group})

                def get_boolean(self, key):
                    return True

            self_test = self
            with (
                patch.object(manage, "APPLICATIONS", applications),
                patch.object(manage, "DATA", root / "data"),
                patch.object(manage, "installed_extension", return_value=root / "system"),
                patch.object(manage, "read_settings", return_value=FolderSettings()),
                patch.object(manage.Gio.Settings, "new", return_value=ShellSettings()),
                patch.object(manage, "compatibility_launchers"),
                patch.object(manage, "install_presentation"),
                patch.object(manage, "refresh_desktop_database"),
                patch.object(manage, "set_extension_enabled", return_value=False),
            ):
                manage.enable()
            self.assertEqual(pinned, [group["id"] + ".desktop"])

    def test_desktop_arguments_reach_the_process_unchanged(self):
        from gi.repository import Gio, GLib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = root / "record.py"
            result = root / "argv.json"
            recorder.write_text(
                "import json,sys; from pathlib import Path; "
                "Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))"
            )
            argument = 'spaces "quotes" \\ slash $d `tick` %f'
            js_argument = subprocess.check_output(
                [
                    "node",
                    "--input-type=module",
                    "-e",
                    "import {quoteDesktopArgument} from './extension/model.js'; "
                    "process.stdout.write(quoteDesktopArgument(process.argv[1]));",
                    argument,
                ],
                cwd=ROOT,
                text=True,
            )
            for quoted in (manage.quote_exec(argument), js_argument):
                result.unlink(missing_ok=True)
                desktop = root / "test.desktop"
                desktop.write_text(
                    "[Desktop Entry]\nType=Application\nName=Test\nExec=/usr/bin/python3 "
                    + manage.quote_exec(recorder)
                    + " "
                    + manage.quote_exec(result)
                    + " "
                    + quoted
                    + "\n"
                )
                app = Gio.DesktopAppInfo.new_from_filename(str(desktop))
                self.assertIsNotNone(app)
                app.launch([], None)
                loop = GLib.MainLoop()

                def completed():
                    if result.exists():
                        loop.quit()
                        return False
                    return True

                poll = GLib.timeout_add(20, completed)
                timeout = GLib.timeout_add_seconds(3, lambda: loop.quit() or False)
                loop.run()
                GLib.source_remove(timeout)
                if not result.exists():
                    GLib.source_remove(poll)
                import json

                self.assertEqual(json.loads(result.read_text()), [argument])

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


if __name__ == "__main__":
    unittest.main()

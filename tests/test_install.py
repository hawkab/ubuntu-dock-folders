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


class InstallTests(unittest.TestCase):
    def test_disable_restores_favorites_without_removing_user_files(self):
        import json
        from gi.repository import Gio

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = manage.read_settings(ROOT / "build/extension")
            group = {"test": {"id": "local.groups.Test", "name": "Tools", "apps": [
                {"desktop": "first.desktop"}, {"desktop": "second.desktop"}]}}
            settings.set_string("groups", json.dumps(group))
            shell = Gio.Settings.new("org.gnome.shell")
            shell.set_strv("favorite-apps", ["local.groups.Test.desktop", "second.desktop", "other.desktop"])
            shell.set_strv("enabled-extensions", [install_context.UUID, "other-extension"])
            launcher = root / "launcher.desktop"
            launcher.write_text("user launcher")
            with patch.object(manage.os, "geteuid", return_value=1000), patch.object(
                    manage, "cleanup_settings", return_value=settings), patch.object(
                    manage.files, "shell_available", return_value=False), patch.object(
                    sys, "argv", ["manage.py", "disable"]), patch.object(
                    manage, "check_requirements", side_effect=AssertionError("Disable requires no active Shell")):
                manage.main()
            self.assertEqual(shell.get_strv("favorite-apps"), ["first.desktop", "second.desktop", "other.desktop"])
            self.assertEqual(shell.get_strv("enabled-extensions"), ["other-extension"])
            self.assertEqual(json.loads(settings.get_string("groups")), group)
            self.assertEqual(launcher.read_text(), "user launcher")

    def test_supported_shell_versions(self):
        with (
            patch.object(manage.os, "geteuid", return_value=1000),
            patch.object(manage.shutil, "which", return_value="/usr/bin/gnome-extensions"),
            patch.object(manage.Path, "exists", return_value=True),
            patch.object(manage.subprocess, "check_output") as version,
        ):
            for value in ("GNOME Shell 46.0", "GNOME Shell 50.1"):
                with self.subTest(version=value):
                    version.return_value = value
                    manage.check_requirements()
            for value in ("GNOME Shell 45.0", "GNOME Shell 47.2", "GNOME Shell 49.0", "GNOME Shell 51.0"):
                with self.subTest(version=value):
                    version.return_value = value
                    with self.assertRaisesRegex(RuntimeError, "Ubuntu 26.04 / GNOME Shell 50.*Ubuntu 24.04 / GNOME Shell 46"):
                        manage.check_requirements()


    def test_disabling_without_a_working_shell_keeps_cleanup_possible(self):
        values = {"enabled-extensions": [install_context.UUID, "other"], "disabled-extensions": []}

        class Settings:
            def get_strv(self, key):
                return values[key][:]

            def set_strv(self, key, value):
                values[key] = value[:]

        with (
            patch.object(manage.Gio.Settings, "new", return_value=Settings()),
            patch.object(manage.shutil, "which", return_value="/usr/bin/gnome-extensions"),
            patch.object(install_context, "shell_available", return_value=True),
            patch.object(manage.subprocess, "run") as run,
        ):
            run.side_effect = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1)]
            manage.set_extension_enabled(False)
            self.assertEqual(values["enabled-extensions"], ["other"])
            self.assertEqual(values["disabled-extensions"], [install_context.UUID])
            self.assertFalse(run.call_args.kwargs["check"])

    def test_uninstall_after_package_removal_preserves_settings_and_expands_favorites(self):
        import os

        code = """
import json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
import manage
import install_context
import settings_integration
from gi.repository import Gio
root=Path(sys.argv[3])
install_context.ROOT=root
schema=root/'extension/schemas/org.gnome.shell.extensions.dock-groups.gschema.xml'
schema.parent.mkdir(parents=True)
schema.write_bytes((Path(sys.argv[2])/'schemas'/schema.name).read_bytes())
settings=manage.read_settings(Path(sys.argv[2]))
groups={'test':{'id':'local.groups.Test','name':'Tools','icon':'folder','apps':[
 {'desktop':'first.desktop','label':'First'},{'desktop':'second.desktop','label':'Second'}]}}
settings.set_string('groups',json.dumps(groups))
shell=Gio.Settings.new('org.gnome.shell')
shell.set_strv('favorite-apps',['local.groups.Test.desktop','second.desktop','other.desktop'])
shell.set_strv('enabled-extensions',[install_context.UUID,'other'])
install_context.SYSTEM_EXTENSION=root/'missing-system-extension'
install_context.APPLICATIONS.mkdir(parents=True)
desktop=install_context.APPLICATIONS/'org.gnome.Settings.desktop'
desktop.write_text('[Desktop Entry]\\nExec=/usr/share/gnome-shell/extensions/dock-groups@local/integration/ubuntu-settings\\n')
group=install_context.APPLICATIONS/'local.groups.Test.desktop'
group.write_text('[Desktop Entry]\\nExec=/usr/bin/python3 /usr/share/gnome-shell/extensions/dock-groups@local/app/launcher.py test\\n')
with patch.object(manage.os,'geteuid',return_value=1000), patch.object(sys,'argv',['manage.py','uninstall']), patch.object(manage,'check_requirements',side_effect=AssertionError('uninstall gated on Shell version')):
 manage.main()
 manage.main()
assert not desktop.exists() and not group.exists()
assert shell.get_strv('favorite-apps')==['first.desktop','second.desktop','other.desktop']
assert shell.get_strv('enabled-extensions')==['other']
assert json.loads(settings.get_string('groups'))==groups
print('UNINSTALL_OK')
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                ["/usr/bin/python3", "-c", code, str(ROOT / "scripts"),
                 str(ROOT / "build/extension"), str(root / "source")],
                env=dict(os.environ, GSETTINGS_BACKEND="memory", XDG_DATA_HOME=str(root / "data"),
                         XDG_CONFIG_HOME=str(root / "config"), XDG_STATE_HOME=str(root / "state")),
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("UNINSTALL_OK", result.stdout)


    def test_running_extension_is_updated_without_hot_reload(self):
        class Settings:
            def get_strv(self, key):
                return [install_context.UUID] if key == "enabled-extensions" else []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            extension = root / "installed"
            extension.mkdir()
            old = extension / "extension.js"
            old.write_text("old")
            inode = old.stat().st_ino
            bundle = root / "dist" / f"{install_context.UUID}.shell-extension.zip"
            bundle.parent.mkdir()
            with zipfile.ZipFile(bundle, "w") as archive:
                archive.writestr("extension.js", "new")
                archive.write(
                    ROOT / "extension/schemas/org.gnome.shell.extensions.dock-groups.gschema.xml",
                    "schemas/org.gnome.shell.extensions.dock-groups.gschema.xml",
                )
            with (
                patch.object(install_context, "ROOT", root),
                patch.object(install_context, "USER_EXTENSION", extension),
                patch.object(manage, "backup", return_value=root / "backup"),
                patch.object(manage.Gio.Settings, "new", return_value=Settings()),
                patch.object(manage, "enable") as enable,
            ):
                manage.install()
                enable.assert_called_once_with(False, activate=False)
            self.assertEqual(old.read_text(), "new")
            self.assertNotEqual(old.stat().st_ino, inode)
            self.assertTrue((extension / "schemas/gschemas.compiled").exists())


    def test_enable_before_shell_discovers_the_extension(self):
        values = {"enabled-extensions": ["other"], "disabled-extensions": [install_context.UUID]}

        class Settings:
            def get_strv(self, key):
                return values[key][:]

            def set_strv(self, key, value):
                values[key] = value[:]

        with patch.object(manage.subprocess, "run") as run:
            run.return_value.returncode = 1
            with patch.object(manage.Gio.Settings, "new", return_value=Settings()):
                self.assertFalse(manage.set_extension_enabled(True))
                self.assertEqual(values["enabled-extensions"], ["other", install_context.UUID])
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
                patch.object(install_context, "APPLICATIONS", applications),
                patch.object(install_context, "DATA", root / "data"),
                patch.object(install_context, "installed_extension", return_value=root / "system"),
                patch.object(manage, "read_settings", return_value=FolderSettings()),
                patch.object(manage.Gio.Settings, "new", return_value=ShellSettings()),
                patch.object(manage, "compatibility_launchers"),
                patch.object(manage, "install_presentation"),
                patch.object(install_context, "refresh_desktop_database"),
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



if __name__ == "__main__":
    unittest.main()

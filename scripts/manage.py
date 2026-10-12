# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Install, enable, or remove the GNOME desktop backend."""

import argparse
import gettext
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from backup import backup, read_settings
from gi.repository import Gio, GLib

import install_context as files
from install_context import atomic_copy, quote_exec
from settings_integration import install_integration, remove_integration, migrate_integration
from desktop_presentation import (install_presentation, remove_presentation)
from gnome_provider import select_system

def expand_favorites(settings):
    groups = json.loads(settings.get_string("groups"))
    membership = {
        group["id"] + ".desktop": [entry["desktop"] for entry in group["apps"]]
        for group in groups.values()
    }
    shell = Gio.Settings.new("org.gnome.shell")
    expanded = []
    for item in shell.get_strv("favorite-apps"):
        expanded.extend(membership.get(item, [item]))
    shell.set_strv("favorite-apps", list(dict.fromkeys(expanded)))
    Gio.Settings.sync()


def check_requirements():
    if os.geteuid() == 0:
        raise RuntimeError("Run this command as your desktop user, without sudo.")
    if not shutil.which("gnome-extensions"):
        raise RuntimeError("GNOME Shell is required.")
    version = subprocess.check_output(["gnome-shell", "--version"], text=True)
    if not re.search(r"\b(?:46|50)\.", version):
        raise RuntimeError("This release supports Ubuntu 26.04 / GNOME Shell 50 and Ubuntu 24.04 / GNOME Shell 46.")
    dock = Path("/usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com")
    if not dock.exists():
        raise RuntimeError("Install gnome-shell-extension-ubuntu-dock first.")


def compatibility_launchers():
    files.DATA.mkdir(parents=True, exist_ok=True)
    for name in ("launcher.py", "preferences.py"):
        shim = "#!/usr/bin/python3\nimport runpy\nimport sys\nfrom pathlib import Path\nfrom gi.repository import GLib\n"
        shim += f'root = Path(GLib.get_user_data_dir()) / "gnome-shell/extensions/{files.UUID}"\n'
        shim += f'if not root.exists(): root = Path("/usr/share/gnome-shell/extensions/{files.UUID}")\n'
        shim += 'sys.path.insert(0, str(root / "app"))\n'
        shim += f'runpy.run_path(str(root / "app/{name}"), run_name="__main__")\n'
        (files.DATA / name).write_text(shim)


def install_group_launchers(extension, groups):
    files.APPLICATIONS.mkdir(parents=True, exist_ok=True)
    files.DATA.mkdir(parents=True, exist_ok=True)
    registry = files.DATA / "group-desktops.json"
    previous = json.loads(registry.read_text()) if registry.exists() else []
    current = []
    translate = gettext.translation(
        "ubuntu-dock-folders", localedir=extension / "locale", fallback=True
    ).gettext
    launcher = quote_exec(extension / "app/launcher.py")
    for key, group in groups.items():
        if not re.fullmatch(r"local\.groups\.[A-Za-z0-9_-]+", group["id"]):
            raise RuntimeError("Invalid group desktop ID")
        filename = group["id"] + ".desktop"
        current.append(filename)
        name = group["name"].replace("\n", " ").replace("\r", " ")
        actions = ""
        for index, entry in enumerate(group["apps"]):
            label = entry["label"].replace("\n", " ").replace("\r", " ")
            actions += (
                f"\n[Desktop Action App{index}]\nName={label}\n"
                f"Exec=/usr/bin/gtk-launch {quote_exec(entry['desktop'])}\n"
            )
        contents = (
            f"[Desktop Entry]\nType=Application\nName={name}\n"
            f"Comment={translate('Choose an application')}\n"
            f"Exec=/usr/bin/python3 {launcher} {quote_exec(key)}\n"
            f"Icon={group['icon']}\nTerminal=false\nStartupNotify=true\nCategories=Utility;\n"
            "Actions=" + "".join(f"App{i};" for i in range(len(group["apps"]))) + "\n" + actions
        )
        destination = files.APPLICATIONS / filename
        if not destination.exists() or destination.read_text() != contents:
            destination.write_text(contents)
    for filename in previous:
        if (
            re.fullmatch(r"local\.groups\.[A-Za-z0-9_-]+\.desktop", filename)
            and filename not in current
        ):
            (files.APPLICATIONS / filename).unlink(missing_ok=True)
    if not registry.exists() or previous != current:
        registry.write_text(json.dumps(current) + "\n")
    files.refresh_desktop_database()


def set_extension_enabled(enabled):
    shell = Gio.Settings.new("org.gnome.shell")
    wanted = [item for item in shell.get_strv("enabled-extensions") if item != files.UUID]
    blocked = [item for item in shell.get_strv("disabled-extensions") if item != files.UUID]
    (wanted if enabled else blocked).append(files.UUID)
    shell.set_strv("enabled-extensions", wanted)
    shell.set_strv("disabled-extensions", blocked)
    known = False
    if shutil.which("gnome-extensions") and files.shell_available():
        try:
            known = subprocess.run(
                ["gnome-extensions", "info", files.UUID],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            ).returncode == 0
        except subprocess.TimeoutExpired:
            pass
    if known:
        try:
            subprocess.run(["gnome-extensions", "enable" if enabled else "disable", files.UUID],
                           check=enabled, timeout=5)
        except subprocess.TimeoutExpired:
            known = False
    return known


def enable(ubuntu_settings=False, activate=True, system=False, backup_directory=None):
    if system:
        activate = activate and not files.shell_available()
        extension = select_system(files, backup, backup_directory)
    else:
        extension = files.installed_extension()
    compatibility_launchers()
    install_presentation(extension)
    if ubuntu_settings:
        install_integration(extension)
    shell = Gio.Settings.new("org.gnome.shell")
    settings = read_settings(extension)
    favorites = list(shell.get_strv("favorite-apps"))
    groups = json.loads(settings.get_string("groups"))
    install_group_launchers(extension, groups)
    if settings.get_boolean("enabled"):
        membership = {
            entry["desktop"]: group["id"] + ".desktop"
            for group in groups.values()
            for entry in group["apps"]
        }
        shell.set_strv(
            "favorite-apps", list(dict.fromkeys(membership.get(item, item) for item in favorites))
        )
    known = set_extension_enabled(True) if activate else True
    Gio.Settings.sync()
    print(
        "Enabled Ubuntu Dock Folders. Log out and back in to load updated Shell code."
        if known
        else "Installed Ubuntu Dock Folders. Log out and back in to load the extension."
    )


def install(ubuntu_settings=False, backup_directory=None):
    bundle = files.ROOT / "dist" / f"{files.UUID}.shell-extension.zip"
    if not bundle.exists():
        raise RuntimeError("Build the repository first: make build")
    saved = backup(backup_directory)
    print("Backup:", saved)
    shell = Gio.Settings.new("org.gnome.shell")
    running = (
        files.USER_EXTENSION.exists()
        and files.UUID in shell.get_strv("enabled-extensions")
        and files.UUID not in shell.get_strv("disabled-extensions")
    )
    if files.USER_EXTENSION.exists():
        with tempfile.TemporaryDirectory(prefix="dock-folders-update-") as directory:
            stage = Path(directory)
            with zipfile.ZipFile(bundle) as archive:
                if any(
                    Path(name).is_absolute() or ".." in Path(name).parts
                    for name in archive.namelist()
                ):
                    raise RuntimeError("Invalid extension bundle paths.")
                archive.extractall(stage)
            subprocess.run(["glib-compile-schemas", "--strict", str(stage / "schemas")], check=True)
            for source in stage.rglob("*"):
                if source.is_file():
                    atomic_copy(source, files.USER_EXTENSION / source.relative_to(stage))
    else:
        subprocess.run(["gnome-extensions", "install", "--force", str(bundle)], check=True)
    if ubuntu_settings:
        for source in (files.ROOT / "build/integration").iterdir():
            atomic_copy(source, files.USER_EXTENSION / "integration" / source.name)
    enable(ubuntu_settings, activate=not running)


def cleanup_settings():
    for extension in (files.USER_EXTENSION, files.SYSTEM_EXTENSION, files.ROOT / "build/extension"):
        if (extension / "schemas/gschemas.compiled").exists():
            return read_settings(extension)
    schema = files.ROOT / "extension/schemas/org.gnome.shell.extensions.dock-groups.gschema.xml"
    if not schema.exists():
        return None
    with tempfile.TemporaryDirectory(prefix="dock-folders-schema-") as directory:
        extension = Path(directory)
        (extension / "schemas").mkdir()
        shutil.copy2(schema, extension / "schemas" / schema.name)
        subprocess.run(["glib-compile-schemas", "--strict", str(extension / "schemas")], check=True)
        return read_settings(extension)


def uninstall(backup_directory=None):
    saved = backup(backup_directory)
    print("Backup:", saved)
    settings = cleanup_settings()
    set_extension_enabled(False)
    if settings:
        expand_favorites(settings)
    remove_integration()
    remove_presentation()
    if files.USER_EXTENSION.exists():
        shutil.rmtree(files.USER_EXTENSION)
    for path in files.APPLICATIONS.glob("local.groups.*.desktop"):
        if files.UUID in path.read_text() or "/launcher-groups/" in path.read_text():
            path.unlink()
    (files.DATA / "group-desktops.json").unlink(missing_ok=True)
    for name in ("launcher.py", "preferences.py"):
        (files.DATA / name).unlink(missing_ok=True)
    files.refresh_desktop_database()
    print(
        "Removed the user extension. Folder settings and wallpaper were retained for reinstallation."
    )


def disable():
    """Disable the extension and restore application favorites without deleting user files."""
    settings = cleanup_settings()
    set_extension_enabled(False)
    if settings:
        expand_favorites(settings)
    print("Disabled Ubuntu Dock Folders. Folder settings were retained.")


def main():
    parser = argparse.ArgumentParser(
        description="Install, enable, or remove Ubuntu Dock Folders for the current user."
    )
    parser.add_argument("command", choices=("install", "enable", "disable", "uninstall", "backup", "repair-settings", "preferences"))
    parser.add_argument(
        "--ubuntu-settings",
        action="store_true",
        help="Add the optional Ubuntu Desktop settings row",
    )
    parser.add_argument("--backup-directory", type=Path)
    parser.add_argument("--system", action="store_true", help="Use the installed system extension after backing up an owned user override")
    args = parser.parse_args()
    if args.system and args.command != "enable":
        parser.error("--system is available for the enable command")
    try:
        if args.command == "backup":
            print(backup(args.backup_directory))
            return
        if args.command in ("disable", "uninstall", "repair-settings", "preferences"):
            if os.geteuid() == 0:
                raise RuntimeError("Run this command as your desktop user, without sudo.")
            if args.command == "disable":
                disable()
            elif args.command == "uninstall":
                uninstall(args.backup_directory)
            elif args.command == "preferences":
                subprocess.run(["gnome-extensions", "prefs", "dock-groups@local"], check=True)
            else:
                migrate_integration()
            return
        check_requirements()
        if args.command == "install":
            install(args.ubuntu_settings, args.backup_directory)
        elif args.command == "enable":
            enable(args.ubuntu_settings, system=args.system, backup_directory=args.backup_directory)
    except (RuntimeError, subprocess.CalledProcessError, GLib.Error) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()

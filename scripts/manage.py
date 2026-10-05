#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Install, enable, or remove Ubuntu Dock Folders for the current user."""

import argparse
import base64
import gettext
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from backup import DATA, SYSTEM_EXTENSION, USER_EXTENSION, UUID, backup, read_settings
from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parent.parent
APPLICATIONS = Path(GLib.get_user_data_dir()) / "applications"
SERVICE = Path(GLib.get_user_data_dir()) / "dbus-1/services/org.gnome.Settings.service"
STATE = DATA / "install-state.json"
APP_ID = "io.github.hawkab.UbuntuDockFolders"


def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix="." + destination.name, delete=False
    ) as temporary:
        path = Path(temporary.name)
    try:
        shutil.copy2(source, path)
        path.replace(destination)
    finally:
        path.unlink(missing_ok=True)


def quote_exec(value, field_codes=True):
    value = str(value)
    if field_codes:
        value = value.replace("%", "%%")
    quoted = '"' + re.sub(r'["`$\\]', lambda match: "\\" + match[0], value) + '"'
    return (
        quoted.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )


def settings_file(path):
    return (
        path == SERVICE
        or path.name == "org.gnome.Settings.desktop"
        or path.name.endswith("panel.desktop")
    )


def state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    result = {"desktop_backups": {}}
    legacy = DATA / "state.json"
    if legacy.exists():
        original = json.loads(legacy.read_text()).get("desktop_backups", {})
        result["desktop_backups"] = {
            name: contents for name, contents in original.items() if settings_file(Path(name))
        }
    return result


def write_state(value):
    DATA.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    STATE.chmod(0o600)


def preserve_settings_override(current, destination):
    contents = destination.read_text() if destination.exists() else None
    originals = current["desktop_backups"]
    if not integration_override(contents):
        originals[str(destination)] = contents
    elif str(destination) not in originals or integration_override(originals[str(destination)]):
        originals[str(destination)] = None


def install_integration(extension):
    integration = extension / "integration"
    if not (integration / "settings-integration.so").exists():
        raise RuntimeError("Build the Ubuntu Settings companion first: make build")
    launcher = DATA / "ubuntu-settings"
    atomic_copy(integration / "ubuntu-settings", launcher)
    launcher.chmod(0o755)
    wrapper = quote_exec(launcher)
    current = state()
    originals = [Path("/usr/share/applications/org.gnome.Settings.desktop")]
    originals.extend(Path("/usr/share/applications").glob("*panel.desktop"))
    APPLICATIONS.mkdir(parents=True, exist_ok=True)
    for source in originals:
        text = source.read_text()
        if not re.search(r"^Exec=gnome-control-center(?: |$)", text, re.M):
            continue
        destination = APPLICATIONS / source.name
        preserve_settings_override(current, destination)
        destination.write_text(
            re.sub(
                r"^Exec=gnome-control-center", lambda _match: "Exec=" + wrapper, text, flags=re.M
            )
        )
    preserve_settings_override(current, SERVICE)
    SERVICE.parent.mkdir(parents=True, exist_ok=True)
    SERVICE.write_text(
        "[D-BUS Service]\nName=org.gnome.Settings\nExec="
        + quote_exec(launcher, field_codes=False)
        + " --gapplication-service\n"
    )
    current["ubuntu_settings"] = True
    write_state(current)
    refresh_desktop_database()
    reload_settings_service()


def integration_override(contents):
    if not contents:
        return False
    return any(
        "ubuntu-settings" in line
        and ("dock-groups@local/integration/" in line or "launcher-groups/" in line)
        for line in contents.splitlines() if line.startswith("Exec=")
    )


def remove_integration():
    current = state()
    candidates = {SERVICE, APPLICATIONS / "org.gnome.Settings.desktop"}
    candidates.update(APPLICATIONS.glob("*panel.desktop"))
    for path in candidates:
        if not path.is_file() or not integration_override(path.read_text()):
            continue
        original = current["desktop_backups"].get(str(path))
        if original is None or integration_override(original):
            path.unlink(missing_ok=True)
        else:
            path.write_text(original)
    current["desktop_backups"] = {}
    current["ubuntu_settings"] = False
    write_state(current)
    (DATA / "ubuntu-settings").unlink(missing_ok=True)
    refresh_desktop_database()
    reload_settings_service()


def migrate_integration():
    candidates = [SERVICE, APPLICATIONS / "org.gnome.Settings.desktop"]
    candidates.extend(APPLICATIONS.glob("*panel.desktop"))
    legacy = f"/gnome-shell/extensions/{UUID}/integration/ubuntu-settings"
    if not any(path.is_file() and legacy in path.read_text() for path in candidates):
        return
    try:
        extension = installed_extension()
    except RuntimeError:
        remove_integration()
        return
    for candidate in (extension, SYSTEM_EXTENSION):
        if (candidate / "integration/settings-integration.so").exists():
            install_integration(candidate)
            return
    remove_integration()


def reload_settings_service():
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "ReloadConfig", None, None, Gio.DBusCallFlags.NONE, 1000, None,
        )
    except GLib.Error:
        pass


def shell_available():
    try:
        result = Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "NameHasOwner", GLib.Variant("(s)", ("org.gnome.Shell",)),
            GLib.VariantType.new("(b)"), Gio.DBusCallFlags.NONE, 1000, None,
        )
        return result.unpack()[0]
    except GLib.Error:
        return False


def install_presentation(extension):
    share = ROOT / "build/package/usr/share"
    if not share.exists():
        share = Path("/usr/share")
    source = share / "metainfo" / f"{APP_ID}.metainfo.xml"
    if not source.exists():
        return
    data = Path(GLib.get_user_data_dir())
    current = state()
    originals = current.setdefault("presentation_backups", {})

    def preserve(destination):
        originals.setdefault(
            str(destination),
            base64.b64encode(destination.read_bytes()).decode() if destination.exists() else None,
        )

    for source_file in (share / "icons/hicolor").glob(f"*/apps/{APP_ID}.*"):
        destination = data / source_file.relative_to(share)
        preserve(destination)
        atomic_copy(source_file, destination)
    desktop = APPLICATIONS / f"{APP_ID}.desktop"
    preserve(desktop)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    text = (share / "applications" / desktop.name).read_text()
    text = re.sub(
        r"^Exec=.*$",
        lambda _match: (
            "Exec=/usr/bin/python3 " + quote_exec(extension / "app/preferences.py") + " --global"
        ),
        text,
        flags=re.M,
    )
    desktop.write_text(text)

    write_state(current)
    refresh_desktop_database()


def remove_presentation():
    current = state()
    for filename, original in current.get("presentation_backups", {}).items():
        path = Path(filename)
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(original))
    current["presentation_backups"] = {}
    write_state(current)
    refresh_desktop_database()


def refresh_desktop_database():
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(APPLICATIONS)], check=True)


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


def installed_extension():
    if USER_EXTENSION.exists():
        return USER_EXTENSION
    if SYSTEM_EXTENSION.exists():
        return SYSTEM_EXTENSION
    raise RuntimeError("The extension is not installed.")


def check_requirements():
    if os.geteuid() == 0:
        raise RuntimeError("Run this command as your desktop user, without sudo.")
    if not shutil.which("gnome-extensions"):
        raise RuntimeError("GNOME Shell is required.")
    version = subprocess.check_output(["gnome-shell", "--version"], text=True)
    if not re.search(r"\b(?:46|50)\.", version):
        raise RuntimeError("This release supports GNOME Shell 46 and 50 on Ubuntu 24.04 and 26.04.")
    dock = Path("/usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com")
    if not dock.exists():
        raise RuntimeError("Install gnome-shell-extension-ubuntu-dock first.")


def compatibility_launchers():
    DATA.mkdir(parents=True, exist_ok=True)
    for name in ("launcher.py", "preferences.py"):
        shim = "#!/usr/bin/python3\nimport runpy\nimport sys\nfrom pathlib import Path\nfrom gi.repository import GLib\n"
        shim += f'root = Path(GLib.get_user_data_dir()) / "gnome-shell/extensions/{UUID}"\n'
        shim += f'if not root.exists(): root = Path("/usr/share/gnome-shell/extensions/{UUID}")\n'
        shim += 'sys.path.insert(0, str(root / "app"))\n'
        shim += f'runpy.run_path(str(root / "app/{name}"), run_name="__main__")\n'
        (DATA / name).write_text(shim)


def install_group_launchers(extension, groups):
    APPLICATIONS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    registry = DATA / "group-desktops.json"
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
        destination = APPLICATIONS / filename
        if not destination.exists() or destination.read_text() != contents:
            destination.write_text(contents)
    for filename in previous:
        if (
            re.fullmatch(r"local\.groups\.[A-Za-z0-9_-]+\.desktop", filename)
            and filename not in current
        ):
            (APPLICATIONS / filename).unlink(missing_ok=True)
    if not registry.exists() or previous != current:
        registry.write_text(json.dumps(current) + "\n")
    refresh_desktop_database()


def set_extension_enabled(enabled):
    shell = Gio.Settings.new("org.gnome.shell")
    wanted = [item for item in shell.get_strv("enabled-extensions") if item != UUID]
    blocked = [item for item in shell.get_strv("disabled-extensions") if item != UUID]
    (wanted if enabled else blocked).append(UUID)
    shell.set_strv("enabled-extensions", wanted)
    shell.set_strv("disabled-extensions", blocked)
    known = False
    if shutil.which("gnome-extensions") and shell_available():
        try:
            known = subprocess.run(
                ["gnome-extensions", "info", UUID],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            ).returncode == 0
        except subprocess.TimeoutExpired:
            pass
    if known:
        try:
            subprocess.run(["gnome-extensions", "enable" if enabled else "disable", UUID],
                           check=enabled, timeout=5)
        except subprocess.TimeoutExpired:
            known = False
    return known


def enable(ubuntu_settings=False, activate=True):
    extension = installed_extension()
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
    bundle = ROOT / "dist" / f"{UUID}.shell-extension.zip"
    if not bundle.exists():
        raise RuntimeError("Build the repository first: make build")
    saved = backup(backup_directory)
    print("Backup:", saved)
    shell = Gio.Settings.new("org.gnome.shell")
    running = (
        USER_EXTENSION.exists()
        and UUID in shell.get_strv("enabled-extensions")
        and UUID not in shell.get_strv("disabled-extensions")
    )
    if USER_EXTENSION.exists():
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
                    atomic_copy(source, USER_EXTENSION / source.relative_to(stage))
    else:
        subprocess.run(["gnome-extensions", "install", "--force", str(bundle)], check=True)
    if ubuntu_settings:
        for source in (ROOT / "build/integration").iterdir():
            atomic_copy(source, USER_EXTENSION / "integration" / source.name)
    enable(ubuntu_settings, activate=not running)


def cleanup_settings():
    for extension in (USER_EXTENSION, SYSTEM_EXTENSION, ROOT / "build/extension"):
        if (extension / "schemas/gschemas.compiled").exists():
            return read_settings(extension)
    schema = ROOT / "extension/schemas/org.gnome.shell.extensions.dock-groups.gschema.xml"
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
    if USER_EXTENSION.exists():
        shutil.rmtree(USER_EXTENSION)
    for path in APPLICATIONS.glob("local.groups.*.desktop"):
        if UUID in path.read_text() or "/launcher-groups/" in path.read_text():
            path.unlink()
    (DATA / "group-desktops.json").unlink(missing_ok=True)
    for name in ("launcher.py", "preferences.py"):
        (DATA / name).unlink(missing_ok=True)
    refresh_desktop_database()
    print(
        "Removed the user extension. Folder settings and wallpaper were retained for reinstallation."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Install, enable, or remove Ubuntu Dock Folders for the current user."
    )
    parser.add_argument("command", choices=("install", "enable", "uninstall", "backup", "repair-settings"))
    parser.add_argument(
        "--ubuntu-settings",
        action="store_true",
        help="Add the optional Ubuntu Desktop settings row",
    )
    parser.add_argument("--backup-directory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            print(backup(args.backup_directory))
            return
        if args.command in ("uninstall", "repair-settings"):
            if os.geteuid() == 0:
                raise RuntimeError("Run this command as your desktop user, without sudo.")
            if args.command == "uninstall":
                uninstall(args.backup_directory)
            else:
                migrate_integration()
            return
        check_requirements()
        if args.command == "install":
            install(args.ubuntu_settings, args.backup_directory)
        elif args.command == "enable":
            enable(args.ubuntu_settings)
    except (RuntimeError, subprocess.CalledProcessError, GLib.Error) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()

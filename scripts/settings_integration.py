# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Install and restore Ubuntu Settings launchers."""

import re
from pathlib import Path
import install_context as context

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
    launcher = context.DATA / "ubuntu-settings"
    context.atomic_copy(integration / "ubuntu-settings", launcher)
    launcher.chmod(0o755)
    wrapper = context.quote_exec(launcher)
    current = context.state()
    originals = [Path("/usr/share/applications/org.gnome.Settings.desktop")]
    originals.extend(Path("/usr/share/applications").glob("*panel.desktop"))
    context.APPLICATIONS.mkdir(parents=True, exist_ok=True)
    for source in originals:
        text = source.read_text()
        if not re.search(r"^Exec=gnome-control-center(?: |$)", text, re.M):
            continue
        destination = context.APPLICATIONS / source.name
        preserve_settings_override(current, destination)
        destination.write_text(
            re.sub(
                r"^Exec=gnome-control-center", lambda _match: "Exec=" + wrapper, text, flags=re.M
            )
        )
    preserve_settings_override(current, context.SERVICE)
    context.SERVICE.parent.mkdir(parents=True, exist_ok=True)
    context.SERVICE.write_text(
        "[D-BUS Service]\nName=org.gnome.Settings\nExec="
        + context.quote_exec(launcher, field_codes=False)
        + " --gapplication-service\n"
    )
    current["ubuntu_settings"] = True
    context.write_state(current)
    context.refresh_desktop_database()
    context.reload_settings_service()


def integration_override(contents):
    if not contents:
        return False
    return any(
        "ubuntu-settings" in line
        and ("dock-groups@local/integration/" in line or "launcher-groups/" in line)
        for line in contents.splitlines() if line.startswith("Exec=")
    )


def remove_integration():
    current = context.state()
    candidates = {context.SERVICE, context.APPLICATIONS / "org.gnome.Settings.desktop"}
    candidates.update(context.APPLICATIONS.glob("*panel.desktop"))
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
    context.write_state(current)
    (context.DATA / "ubuntu-settings").unlink(missing_ok=True)
    context.refresh_desktop_database()
    context.reload_settings_service()


def migrate_integration():
    candidates = [context.SERVICE, context.APPLICATIONS / "org.gnome.Settings.desktop"]
    candidates.extend(context.APPLICATIONS.glob("*panel.desktop"))
    legacy = f"/gnome-shell/extensions/{context.UUID}/integration/ubuntu-settings"
    if not any(path.is_file() and legacy in path.read_text() for path in candidates):
        return
    try:
        extension = context.installed_extension()
    except RuntimeError:
        remove_integration()
        return
    for candidate in (extension, context.SYSTEM_EXTENSION):
        if (candidate / "integration/settings-integration.so").exists():
            install_integration(candidate)
            return
    remove_integration()

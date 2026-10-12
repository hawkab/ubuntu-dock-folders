#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Restore managed Plasma panels and stop owned helpers before removal."""

import os
import pwd
import subprocess
from pathlib import Path


def remove():
    if os.environ.get("DPKG_ROOT"):
        return
    for user in pwd.getpwall():
        if not 1000 <= user.pw_uid < 65534:
            continue
        home = Path(user.pw_dir)
        data = home / ".local/share"
        if not any(path.exists() for path in (
                home / ".local/state/ubuntu-dock-folders/plasma-panel.json",
                data / "plasma/plasmoids/io.github.hawkab.DockFolders",
                data / "dbus-1/services/io.github.hawkab.DockFolders.Plasma.service")):
            continue
        runtime = Path("/run/user") / str(user.pw_uid)
        environment = dict(os.environ, HOME=user.pw_dir, USER=user.pw_name, LOGNAME=user.pw_name,
                           XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(data),
                           XDG_STATE_HOME=str(home / ".local/state"), XDG_CURRENT_DESKTOP="KDE")
        environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        command = ["/usr/bin/python3", str(Path(__file__).with_name("plasma_manage.py")), "uninstall"]
        if (runtime / "bus").exists():
            environment.update(XDG_RUNTIME_DIR=str(runtime),
                               DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(runtime / "bus"))
        else:
            environment.pop("XDG_RUNTIME_DIR", None)
            command = ["dbus-run-session", "--", *command]
        subprocess.run(["runuser", "-u", user.pw_name, "--", *command], env=environment,
                       check=True, timeout=30)


if __name__ == "__main__":
    remove()

#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Remove user-owned GNOME integrations before package files disappear."""

import os
import pwd
import subprocess
from pathlib import Path


def users():
    """Yield desktop users with files owned by this installation."""
    for user in pwd.getpwall():
        if not 1000 <= user.pw_uid < 65534:
            continue
        home = Path(user.pw_dir)
        data = home / ".local/share"
        if (data / "launcher-groups/install-state.json").exists() or (data / "gnome-shell/extensions/dock-groups@local").exists():
            yield user


def remove():
    if os.environ.get("DPKG_ROOT"):
        return
    script = Path(__file__).with_name("manage.py")
    for user in users():
        runtime = Path("/run/user") / str(user.pw_uid)
        environment = dict(os.environ, HOME=user.pw_dir, USER=user.pw_name, LOGNAME=user.pw_name,
                           XDG_DATA_HOME=str(Path(user.pw_dir) / ".local/share"),
                           XDG_CONFIG_HOME=str(Path(user.pw_dir) / ".config"),
                           XDG_STATE_HOME=str(Path(user.pw_dir) / ".local/state"), XDG_CURRENT_DESKTOP="GNOME")
        environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        command = ["/usr/bin/python3", str(script), "uninstall"]
        if (runtime / "bus").exists():
            environment.update(XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(runtime / "bus"))
        else:
            environment.pop("XDG_RUNTIME_DIR", None)
            command = ["dbus-run-session", "--", *command]
        subprocess.run(["runuser", "-u", user.pw_name, "--", *command], env=environment, check=True, timeout=30)


if __name__ == "__main__":
    remove()

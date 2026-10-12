#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Restore Xfce panel slots before uninstalling the plugin."""

import os
import pwd
import subprocess
from pathlib import Path


def remove():
    if os.environ.get("DPKG_ROOT"):
        return
    for user in pwd.getpwall():
        home=Path(user.pw_dir)
        if not 1000 <= user.pw_uid < 65534 or not any(path.exists() for path in (
                home/".local/share/launcher-groups/xfce-panel.json",
                home/".config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml")):
            continue
        runtime=Path("/run/user")/str(user.pw_uid)
        env=dict(os.environ,HOME=user.pw_dir,USER=user.pw_name,LOGNAME=user.pw_name,
                 XDG_CONFIG_HOME=str(home/".config"),XDG_DATA_HOME=str(home/".local/share"),
                 XDG_STATE_HOME=str(home/".local/state"),XDG_CURRENT_DESKTOP="XFCE")
        command=["/usr/bin/python3",str(Path(__file__).with_name("xfce_manage.py")),"disable"]
        if (runtime/"bus").exists():
            env.update(XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS="unix:path="+str(runtime/"bus"))
        else:
            env.pop("DBUS_SESSION_BUS_ADDRESS",None)
            env.pop("XDG_RUNTIME_DIR",None)
            command=["dbus-run-session","--",*command]
        subprocess.run(["runuser","-u",user.pw_name,"--",*command],env=env,check=True,timeout=30)


if __name__ == "__main__":
    remove()

#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Remove owned desktop integrations before the combined package is removed."""

import os
import subprocess
from pathlib import Path


def remove():
    if os.environ.get("DPKG_ROOT"):
        return
    share = Path("/usr/share/ubuntu-dock-folders")
    for script in (share / "plasma-management/plasma_package_lifecycle.py",
                   share / "xfce-management/xfce_package_lifecycle.py",
                   share / "scripts/package_lifecycle.py"):
        subprocess.run(["/usr/bin/python3", "-I", str(script)], check=True, timeout=40)


if __name__ == "__main__":
    remove()

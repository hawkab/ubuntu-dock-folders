# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Refresh a systemd-managed Plasma widget while its shell is stopped."""

import shutil
import subprocess
import time
import plasma_provider
from plasma_removal import remove_locales

UNIT = "plasma-plasmashell.service"


def managed_shell():
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", UNIT],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5).returncode == 0


def refresh(manager, saved, panel, installed):
    """Upgrade with rollback; keep widget identity, configuration, and placement."""
    previous = saved / "plasma-widget"
    had_override = installed.exists()
    if had_override:
        shutil.copytree(installed, previous, symlinks=True)
    package = manager.package_path()
    system = package == plasma_provider.SYSTEM_PACKAGE
    try:
        subprocess.run(["systemctl", "--user", "stop", UNIT], check=True, timeout=20)
        manager.stop_helper()
        try:
            if system:
                if had_override:
                    remove_locales(installed, manager.DATA)
                    shutil.rmtree(installed)
                manager.write_service(package)
            else:
                action = "--upgrade" if had_override else "--install"
                subprocess.run(["kpackagetool6", "--type", "Plasma/Applet", action,
                                str(package)], check=True, timeout=20)
                manager.write_service(installed)
                manager.install_locales(installed)
        except BaseException:
            if had_override:
                if system:
                    shutil.copytree(previous, installed, dirs_exist_ok=True, symlinks=True)
                    manager.write_service(installed)
                else:
                    subprocess.run(["kpackagetool6", "--type", "Plasma/Applet", "--upgrade", str(previous)],
                                   check=True, timeout=20)
                manager.install_locales(installed)
            raise
    finally:
        subprocess.run(["systemctl", "--user", "start", UNIT], check=True, timeout=20)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        try:
            current = next(item for item in manager.snapshot() if item["id"] == panel["id"])
            if current["order"] != panel["order"] or current["height"] != panel["height"]:
                raise RuntimeError("The panel layout changed during update. The backup was retained.")
            return
        except (manager.GLib.Error, StopIteration):
            time.sleep(.1)
    raise RuntimeError("Plasma did not become ready after update. The backup was retained.")

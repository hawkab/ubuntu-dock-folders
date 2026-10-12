#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Stop all tagged test processes before their private D-Bus session closes."""

import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

MARKER = "DOCK_FOLDERS_TEST_SESSION"


def update_activation_environment(environment=None):
    """Give services on the private test bus the newly created display."""
    if not os.environ.get(MARKER) or not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        raise ValueError("Display activation requires a supervised test bus.")
    environment = environment or os.environ
    keys = ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM", "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", MARKER)
    subprocess.run(["dbus-update-activation-environment",
                    *[key + "=" + environment.get(key, "") for key in keys]], check=True, timeout=3)


def processes(marker):
    """Return same-user processes carrying this test's exact session marker."""
    found = []
    expected = (MARKER + "=" + marker).encode()
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit() or int(directory.name) == os.getpid():
            continue
        try:
            if directory.stat().st_uid == os.getuid() and expected in (directory / "environ").read_bytes().split(b"\0"):
                found.append(int(directory.name))
        except OSError:
            pass
    return found


def stop_processes(marker, excluded=()):
    """Terminate only this test's descendants while keeping its bus alive."""
    targets = set(processes(marker)) - set(excluded)
    servers = set()
    for pid in targets:
        try:
            name = Path(f"/proc/{pid}/comm").read_text().strip()
            if name in {"gnome-shell", "Xwayland", "Xvfb", "kwin_wayland", "kwin_x11", "labwc"}:
                servers.add(pid)
        except OSError:
            pass
    for stage in (targets - servers, servers):
        terminate_processes(stage, marker)


def terminate_processes(targets, marker):
    """Wait for tagged processes to exit before escalating their termination."""
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and targets & set(processes(marker)):
        time.sleep(.05)
    for pid in targets & set(processes(marker)):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_isolated(command, env, timeout, capture=False):
    marker = uuid.uuid4().hex
    private = dict(env, **{MARKER: marker, "DOCK_FOLDERS_TEST_TIMEOUT": str(timeout)})
    home = Path(private["HOME"])
    if home.resolve() == Path.home().resolve():
        raise ValueError("A desktop check requires a temporary home.")
    runtime = home / "runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    private["XDG_RUNTIME_DIR"] = str(runtime)
    for name in ("GNOME_KEYRING_CONTROL", "GNOME_KEYRING_PID", "SSH_AUTH_SOCK", "GPG_AGENT_INFO",
                 "AT_SPI_BUS_ADDRESS", "SESSION_MANAGER", "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE"):
        private.pop(name, None)
    disable_desktop_services(private["XDG_DATA_HOME"])
    try:
        return subprocess.run(["dbus-run-session", "--", "/usr/bin/python3", str(Path(__file__).resolve()),
                               "--supervise", *command], env=private, check=True, timeout=timeout + 8,
                              stdout=subprocess.PIPE if capture else None,
                              stderr=subprocess.STDOUT if capture else None, text=True)
    except subprocess.CalledProcessError as error:
        if capture and error.stdout:
            print(error.stdout, end="", flush=True)
        raise
    finally:
        stop_processes(marker)


def supervise(command):
    child = subprocess.Popen(command)
    result = 1
    try:
        result = child.wait(timeout=float(os.environ["DOCK_FOLDERS_TEST_TIMEOUT"]))
    finally:
        marker = os.environ[MARKER]
        parent = os.getppid()
        bus = []
        for pid in processes(marker):
            try:
                if Path(f"/proc/{pid}/comm").read_text().strip() == "dbus-daemon":
                    bus.append(pid)
            except OSError:
                pass
        stop_processes(marker, [parent, *bus])
    return result


def disable_desktop_services(data):
    """Prevent unrelated hardware and settings daemons in a test desktop."""
    directory = Path(data) / "dbus-1/services"
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("org.kde.kded6", "org.bluez.obex", "org.freedesktop.secrets",
                 "org.freedesktop.impl.portal.Secret", "org.gnome.keyring",
                 "org.gnome.keyring.SystemPrompter", "org.gnome.keyring.PrivatePrompter", "org.kde.kwalletd6"):
        (directory / (name + ".service")).write_text(f"[D-BUS Service]\nName={name}\nExec=/bin/false\n")


if __name__ == "__main__":
    raise SystemExit(supervise(sys.argv[2:]))

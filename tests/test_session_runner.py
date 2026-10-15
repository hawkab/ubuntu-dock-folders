# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Keep test desktops away from the user's runtime and password services."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from session_runner import MARKER, run_isolated, stop_processes, update_activation_environment


class SessionRunnerTests(unittest.TestCase):
    def test_display_activation_cannot_change_an_unsupervised_bus(self):
        with patch.dict(os.environ, {"DBUS_SESSION_BUS_ADDRESS": "host-bus"}, clear=True), \
                patch("session_runner.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "supervised"):
                update_activation_environment()
            run.assert_not_called()

    def test_display_activation_exports_only_test_display_variables(self):
        environment = {MARKER: "private", "DBUS_SESSION_BUS_ADDRESS": "private-bus",
                       "DISPLAY": ":123", "XAUTHORITY": "/tmp/private-auth", "WAYLAND_DISPLAY": "private-socket", "PRIVATE_TOKEN": "secret"}
        with patch.dict(os.environ, environment, clear=True), patch("session_runner.subprocess.run") as run:
            update_activation_environment()
        arguments = run.call_args.args[0]
        self.assertIn("DISPLAY=:123", arguments)
        self.assertIn("XAUTHORITY=/tmp/private-auth", arguments)
        self.assertIn("WAYLAND_DISPLAY=private-socket", arguments)
        self.assertTrue(all("secret" not in argument for argument in arguments))

    def test_clients_finish_before_their_display_server_is_stopped(self):
        code = '''
import ctypes,signal,sys,time
from pathlib import Path
ctypes.CDLL(None).prctl(15,sys.argv[1].encode(),0,0,0)
def finish(*args):
 if sys.argv[1]=='test-client': time.sleep(.15)
 with open(sys.argv[2],'a') as log: log.write(sys.argv[1]+'\\n')
 raise SystemExit(0)
signal.signal(signal.SIGTERM,finish)
Path(sys.argv[3]).touch()
while True: time.sleep(.05)
'''
        with tempfile.TemporaryDirectory() as directory:
            marker = uuid.uuid4().hex
            root = Path(directory)
            children = [subprocess.Popen([sys.executable, "-c", code, name, str(root/"order"), str(root/name)],
                env=dict(os.environ, **{MARKER: marker})) for name in ("Xwayland", "test-client")]
            try:
                deadline = time.monotonic() + 3
                while not all((root/name).exists() for name in ("Xwayland", "test-client")):
                    self.assertLess(time.monotonic(), deadline, "Cleanup fixture did not start")
                    time.sleep(.01)
                stop_processes(marker)
                self.assertEqual((root/"order").read_text().splitlines(), ["test-client", "Xwayland"])
                for child in children:
                    self.assertEqual(child.wait(timeout=1), 0)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.wait()

    def test_runtime_and_credential_sockets_are_private(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            env = dict(os.environ, HOME=directory, XDG_DATA_HOME=str(home / "data"),
                       GNOME_KEYRING_CONTROL="host-keyring", SSH_AUTH_SOCK="host-ssh",
                       GPG_AGENT_INFO="host-gpg", AT_SPI_BUS_ADDRESS="host-accessibility")
            code = "import json,os;print(json.dumps({k:os.environ.get(k) for k in ['XDG_RUNTIME_DIR','GNOME_KEYRING_CONTROL','SSH_AUTH_SOCK','GPG_AGENT_INFO','AT_SPI_BUS_ADDRESS']}))"
            result = run_isolated(["/usr/bin/python3", "-c", code], env, 5, capture=True)
            value = json.loads(result.stdout)
            self.assertEqual(value.pop("XDG_RUNTIME_DIR"), str(home / "runtime"))
            self.assertTrue(all(item is None for item in value.values()))
            self.assertEqual((home / "runtime").stat().st_mode & 0o777, 0o700)
            service = home / "data/dbus-1/services/org.freedesktop.secrets.service"
            self.assertIn("Exec=/bin/false", service.read_text())

    def test_session_has_no_deadline_unless_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, HOME=directory, XDG_DATA_HOME=str(Path(directory) / "data"),
                       DOCK_FOLDERS_TEST_TIMEOUT="0.001")
            result = run_isolated(
                ["/usr/bin/python3", "-c",
                 "import os,time; time.sleep(.1); print(os.environ.get('DOCK_FOLDERS_TEST_TIMEOUT'))"],
                env, capture=True,
            )
            self.assertEqual(result.stdout.strip(), "None")

    def test_real_home_is_rejected_before_starting_a_desktop(self):
        with self.assertRaisesRegex(ValueError, "temporary home"):
            run_isolated(["/usr/bin/true"], dict(os.environ, HOME=str(Path.home())), 5)

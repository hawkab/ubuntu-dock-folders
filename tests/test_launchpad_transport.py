# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check safe SFTP recovery before source files are written."""

import sys
import errno
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import launchpad_transport


class SftpRecoveryTests(unittest.TestCase):
    def paramiko(self, failures):
        class SSHException(Exception):
            pass

        class AuthenticationException(SSHException):
            pass

        class BadHostKeyException(SSHException):
            pass

        class NoValidConnectionsError(OSError):
            pass

        clients = [MagicMock() for _ in range(len(failures) + 1)]
        for client, error in zip(clients, failures):
            client.connect.side_effect = error
        module = SimpleNamespace(SSHClient=MagicMock(side_effect=clients), RejectPolicy=MagicMock(),
            SSHException=SSHException, AuthenticationException=AuthenticationException,
            BadHostKeyException=BadHostKeyException,
            ssh_exception=SimpleNamespace(NoValidConnectionsError=NoValidConnectionsError))
        return module, clients

    def test_connect_recovers_after_an_outage_and_closes_failed_clients(self):
        module, clients = self.paramiko([TimeoutError("timed out")] * 8)
        with patch.dict(sys.modules, {"paramiko": module}), \
                patch.object(launchpad_transport.time, "sleep") as sleep:
            with launchpad_transport.sftp_session({"launchpad_owner": "example"}, Path("key")) as remote:
                self.assertIs(remote, clients[-1].open_sftp.return_value)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [5, 10, 20, 40, 80, 160, 300, 300])
        for client in clients:
            client.close.assert_called_once()
            client.set_missing_host_key_policy.assert_called_once_with(module.RejectPolicy.return_value)
        for client in clients[:-1]:
            client.open_sftp.assert_not_called()

    def test_authentication_and_host_key_failures_stop_immediately(self):
        for name in ("AuthenticationException", "BadHostKeyException"):
            module, clients = self.paramiko([])
            error = getattr(module, name)("rejected")
            clients[0].connect.side_effect = error
            with self.subTest(error=name), patch.dict(sys.modules, {"paramiko": module}), \
                    patch.object(launchpad_transport.time, "sleep") as sleep:
                with self.assertRaises(type(error)):
                    with launchpad_transport.sftp_session({"launchpad_owner": "example"}, Path("key")):
                        self.fail("Rejected connection was used")
            sleep.assert_not_called()
            clients[0].close.assert_called_once()

    def test_failure_after_transfer_starts_does_not_resubmit(self):
        module, clients = self.paramiko([])
        with patch.dict(sys.modules, {"paramiko": module}), \
                patch.object(launchpad_transport.time, "sleep") as sleep:
            with self.assertRaises(TimeoutError):
                with launchpad_transport.sftp_session({"launchpad_owner": "example"}, Path("key")):
                    raise TimeoutError("write acknowledgement lost")
        module.SSHClient.assert_called_once()
        sleep.assert_not_called()
        clients[0].close.assert_called_once()

    def test_unreachable_network_recovers_before_opening_a_channel(self):
        module, clients = self.paramiko([OSError(errno.ENETUNREACH, "Network is unreachable")])
        with patch.dict(sys.modules, {"paramiko": module}), \
                patch.object(launchpad_transport.time, "sleep") as sleep:
            with launchpad_transport.sftp_session({"launchpad_owner": "example"}, Path("key")):
                pass
        self.assertEqual(module.SSHClient.call_count, 2)
        sleep.assert_called_once_with(5)
        clients[0].open_sftp.assert_not_called()

    def test_channel_setup_failure_recovers_before_any_write(self):
        module, clients = self.paramiko([None])
        clients[0].open_sftp.side_effect = TimeoutError("channel setup timed out")
        with patch.dict(sys.modules, {"paramiko": module}), \
                patch.object(launchpad_transport.time, "sleep") as sleep:
            with launchpad_transport.sftp_session({"launchpad_owner": "example"}, Path("key")):
                pass
        sleep.assert_called_once_with(5)
        clients[0].close.assert_called_once()

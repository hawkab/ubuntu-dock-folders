# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Open authenticated SFTP sessions, retrying only before a transfer starts."""

import errno
import socket
import time
from contextlib import closing, contextmanager

import release_context as context


@contextmanager
def sftp_session(settings, identity):
    """Yield a verified SFTP connection; transfer errors propagate without resubmission."""
    import paramiko

    delay = 5
    while True:
        client = paramiko.SSHClient()
        try:
            client.load_host_keys(str(context.ROOT / "packaging/launchpad-known-hosts"))
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            client.connect(
                "ppa.launchpad.net", username=settings["launchpad_owner"],
                key_filename=str(identity), allow_agent=False, look_for_keys=False,
                timeout=15, auth_timeout=15, banner_timeout=15,
            )
            remote = client.open_sftp()
            remote.get_channel().settimeout(120)
            break
        except (OSError, EOFError, paramiko.SSHException) as error:
            client.close()
            temporary = isinstance(error, (TimeoutError, ConnectionError, socket.gaierror, EOFError,
                                           paramiko.ssh_exception.NoValidConnectionsError))
            temporary |= getattr(error, "errno", None) in {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN}
            temporary |= str(error).startswith(("Error reading SSH protocol banner", "Authentication timeout"))
            if not temporary:
                raise
            print(f"Launchpad SFTP unavailable before transfer; retrying in {delay}s", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 300)
    with closing(client), closing(remote):
        yield remote

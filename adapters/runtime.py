# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Transport the portable API to a persistent GJS worker for GTK adapters."""

import json
import os
import selectors
import subprocess
import time
from pathlib import Path
try:
    from .dependency import verify_core
except ImportError:
    from dependency import verify_core


class CoreRuntime:
    """Exchange newline-delimited JSON with a worker under a single two-second deadline."""

    TIMEOUT = 2
    MAX_REPLY = 16 * 1024 * 1024
    STDERR_TAIL = 4096
    STOP_TIMEOUT = .25

    def __init__(self, directory=None, command=None):
        source = Path(directory) / "adapters" if directory else Path(__file__).resolve().parent
        verify_core(source.parent)
        self.process = subprocess.Popen(command or ["gjs", "-m", str(source / "runner.js")], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self.reader = selectors.DefaultSelector()
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            os.set_blocking(pipe.fileno(), False)
        self.reader.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        self.reader.register(self.process.stderr, selectors.EVENT_READ, "stderr")
        self.stderr = b""
        self.closed = False

    def _exchange(self, request):
        deadline, offset, response = time.monotonic() + self.TIMEOUT, 0, bytearray()
        self.reader.register(self.process.stdin, selectors.EVENT_WRITE, "stdin")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Folder core did not respond within two seconds")
            events = self.reader.select(remaining)
            for key, _mask in events:
                try:
                    if key.data == "stdin":
                        offset += os.write(key.fd, request[offset:offset + 65536])
                        if offset == len(request):
                            self.reader.unregister(self.process.stdin)
                        continue
                    chunk = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if key.data == "stderr":
                    if not chunk:
                        self.reader.unregister(self.process.stderr)
                    self.stderr = (self.stderr + chunk)[-self.STDERR_TAIL:]
                    continue
                if not chunk:
                    detail = self.stderr.decode("utf-8", errors="replace").strip()
                    raise RuntimeError("Folder core stopped" + (": " + detail if detail else ""))
                response.extend(chunk)
                if len(response) > self.MAX_REPLY:
                    raise ValueError("Folder core response exceeded 16 MiB")
                newline = response.find(b"\n")
                if newline >= 0:
                    return json.loads(response[:newline])

    def call(self, method, value=None):
        if self.closed:
            raise RuntimeError("Folder core is closed")
        try:
            request = (json.dumps({"method": method, "value": value}, ensure_ascii=False) + "\n").encode("utf-8")
            reply = self._exchange(request)
            if not isinstance(reply, dict) or not isinstance(reply.get("ok"), bool):
                raise ValueError("Folder core returned an invalid response")
            if not reply["ok"]:
                raise ValueError(str(reply.get("error", "Folder core rejected the request")))
            if "result" not in reply:
                raise ValueError("Folder core returned an incomplete response")
            return reply["result"]
        except (OSError, ValueError, TimeoutError, RuntimeError):
            self.close()
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.reader.close()
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=self.STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=self.STOP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    try:
                        self.process.wait(timeout=self.STOP_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        pass
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            if not pipe.closed:
                pipe.close()

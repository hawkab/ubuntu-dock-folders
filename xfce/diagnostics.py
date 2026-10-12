# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Record embedded Python errors when the panel redirects its standard streams."""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from gi.repository import GLib


class ErrorStream:
    def __init__(self, logger):
        self.logger = logger
        self.buffer = ""

    def write(self, text):
        self.buffer += text
        lines = self.buffer.split("\n")
        self.buffer = lines.pop()[-8192:]
        for line in lines:
            if line.strip():
                self.logger.error(line[:8192])
        return len(text)

    def flush(self):
        if self.buffer:
            self.logger.error(self.buffer)
            self.buffer = ""


def install_logging():
    """Write a bounded per-user error log without modifying the panel's C logging."""
    logger = logging.getLogger("ubuntu-dock-folders.xfce")
    if logger.handlers:
        return
    directory = Path(GLib.get_user_state_dir()) / "ubuntu-dock-folders"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(directory / "xfce.log", maxBytes=262144,
                                                  backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if os.environ.get("DOCK_FOLDERS_DEBUG") == "1" else logging.WARNING)
    logger.propagate = False
    sys.stderr = ErrorStream(logger)

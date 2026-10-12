# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Bound image dimensions and hash files without loading their contents into memory."""

import hashlib
import gi
gi.require_version("GdkPixbuf","2.0")
from gi.repository import GdkPixbuf


def image_info(path):
    """Return image metadata when its decoded size fits the wallpaper budget."""
    info = GdkPixbuf.Pixbuf.get_file_info(str(path))
    return info if info[0] and 0 < info[1]*info[2] <= 16777216 else None


def file_digest(path):
    """Return the SHA-256 of a file read in bounded chunks."""
    digest = hashlib.sha256()
    with open(path,"rb") as stream:
        for chunk in iter(lambda: stream.read(65536),b""):
            digest.update(chunk)
    return digest.hexdigest()

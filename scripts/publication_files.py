# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Select source files and documentation media for distribution."""

import shutil
from pathlib import PurePosixPath

MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm"}


def source_file(name):
    """Return whether a checkout path belongs in a source release."""
    path = PurePosixPath(name)
    if path.parts[0] in {"build", "dist", "reports", "outputs", "backups"}:
        return False
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return name == "README.md"
    if suffix == ".log":
        return False
    return path.parts[0] != "docs" or suffix in MEDIA_SUFFIXES


def copy_media(source, destination):
    """Copy documentation media while keeping notes and logs out of packages."""
    destination.mkdir(parents=True, exist_ok=True)
    for file in sorted(source.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in MEDIA_SUFFIXES:
            continue
        if not file.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"Documentation media leaves its source directory: {file.name}")
        target = destination / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)

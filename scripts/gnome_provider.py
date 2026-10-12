# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Switch an installer-owned GNOME user extension to the system package explicitly."""

import json
import shutil


def select_system(context, backup, directory=None):
    """Back up an owned user override and return the installed system extension."""
    if not (context.SYSTEM_EXTENSION / "metadata.json").is_file():
        raise RuntimeError("Install the Ubuntu Dock Folders Debian package first.")
    if not context.USER_EXTENSION.exists():
        return context.SYSTEM_EXTENSION
    try:
        metadata = json.loads((context.USER_EXTENSION / "metadata.json").read_text())
        state = context.state() if context.STATE.is_file() else {}
        owned = (isinstance(metadata, dict) and isinstance(state, dict)
                 and metadata.get("uuid") == context.UUID and (state.get("ubuntu_settings") is True
                 or any(isinstance(state.get(key), dict) and state[key]
                        for key in ("presentation_backups", "desktop_backups"))))
    except (OSError, ValueError):
        owned = False
    if not owned or context.USER_EXTENSION.is_symlink():
        raise RuntimeError("A user-installed extension shadows the system package. "
                           "Back up or remove that extension before using --system.")
    saved = backup(directory, context.USER_EXTENSION)
    shutil.move(context.USER_EXTENSION, saved / "gnome-user-extension")
    print("Moved the managed user extension to its backup:", saved)
    return context.SYSTEM_EXTENSION

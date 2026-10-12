# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Install and restore the application entry and icons."""

import base64
import re
from pathlib import Path
import install_context as context
from gi.repository import GLib

def install_presentation(extension):
    share = context.ROOT / "build/package/usr/share"
    if not share.exists():
        share = Path("/usr/share")
    source = share / "metainfo" / f"{context.APP_ID}.metainfo.xml"
    if not source.exists():
        return
    data = Path(GLib.get_user_data_dir())
    current = context.state()
    originals = current.setdefault("presentation_backups", {})

    def preserve(destination):
        originals.setdefault(
            str(destination),
            base64.b64encode(destination.read_bytes()).decode() if destination.exists() else None,
        )

    for source_file in (share / "icons/hicolor").glob(f"*/apps/{context.APP_ID}.*"):
        destination = data / source_file.relative_to(share)
        preserve(destination)
        context.atomic_copy(source_file, destination)
    desktop = context.APPLICATIONS / f"{context.APP_ID}.desktop"
    preserve(desktop)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    text = (share / "applications" / desktop.name).read_text()
    text = re.sub(
        r"^Exec=.*$",
        lambda _match: (
            "Exec=/usr/bin/python3 " + context.quote_exec(extension / "app/preferences.py") + " --global"
        ),
        text,
        flags=re.M,
    )
    desktop.write_text(text)

    context.write_state(current)
    context.refresh_desktop_database()


def remove_presentation():
    current = context.state()
    for filename, original in current.get("presentation_backups", {}).items():
        path = Path(filename)
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(original))
    current["presentation_backups"] = {}
    context.write_state(current)
    context.refresh_desktop_database()

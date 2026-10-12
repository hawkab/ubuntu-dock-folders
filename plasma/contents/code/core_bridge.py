# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Execute the shared JavaScript folder API through Plasma's Qt runtime."""

import uuid
import sys
from pathlib import Path

CONTENTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CONTENTS / "adapters"))
from dependency import verify_core
from runtime import CoreRuntime
verify_core(CONTENTS)

_worker = None


def execute(groups, favorites, undo, command, lookup):
    """Resolve application metadata, execute one transaction, and return its JSON result."""
    ids = {entry["desktop"] for group in groups.values() for entry in group["apps"]}
    ids.update(favorites)
    if undo:
        ids.update(undo["before"]["favorites"])
        ids.update(entry["desktop"] for group in undo["before"]["groups"].values() for entry in group["apps"])
    ids.update(command.get("apps", []))
    ids.update(value for key in ("desktop", "target") if isinstance(value := command.get(key), str))
    if command.get("operation") in {"appearance", "applyAppearance"}:
        ids = set()
    entries = {}
    for desktop in ids:
        info = lookup(desktop)
        if info and not desktop.startswith("local.groups."):
            entries[desktop] = {"desktop": desktop, "label": info.get_name()}
    request = {"state": {"groups": groups, "favorites": favorites, "undo": undo},
               "command": command, "entries": entries, "token": uuid.uuid4().hex[:12]}
    return invoke("transaction", request)


def invoke(method, value):
    """Call one exported portable API through the isolated Qt worker."""
    global _worker
    exported = {"transaction":"transact", "folderCatalog":"folderCatalog", "folderCommand":"folderCommand",
                "folderChanges":"describeChanges"}[method]
    if _worker is None or _worker.closed:
        _worker = CoreRuntime(CONTENTS,[str(CONTENTS / "code/dock-folders-core-runner"),
                                       str(CONTENTS / "core/engine.js"),"--server"])
    return _worker.call(exported,value)


def close():
    """Stop the backend's worker and close its pipes."""
    if _worker is not None:
        _worker.close()

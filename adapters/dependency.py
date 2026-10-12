# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check that a frontend ships one complete version of the common core."""

import hashlib
import json
from pathlib import Path


def verify_core(directory):
    core = Path(directory) / "core"
    manifest = json.loads((core / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        if Path(name).name != name or hashlib.sha256((core / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Dock folders core is incomplete or belongs to another build")
    if json.loads((core / "contract.json").read_text())["version"] != manifest["api"]:
        raise RuntimeError("Dock folders core API does not match its contract")
    return manifest

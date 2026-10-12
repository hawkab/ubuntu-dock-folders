# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Read complete JSON probe records while a compositor appends its log."""

import json
from pathlib import Path


def records(path, prefix):
    marker = (prefix + " ").encode()
    result = []
    for line in Path(path).read_bytes().splitlines(keepends=True):
        if not line.endswith(b"\n"):
            continue
        payload = line.partition(marker)[2]
        if payload:
            result.append(json.loads(payload))
    return result

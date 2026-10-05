# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Keep catalog metadata readable by Ubuntu 24.04 software centers."""

import copy


def add_legacy_developer(component):
    developer = component.find("developer")
    if developer is None:
        return
    for name in developer.findall("name"):
        legacy = copy.deepcopy(name)
        legacy.tag = "developer_name"
        component.append(legacy)

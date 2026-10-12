# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Create available, distinct applications for native folder layout checks."""

import json


def prepare(settings, applications):
    groups = json.loads(settings.get_string("groups"))
    for key, count in (("wide", 6), ("four", 4), ("five", 5), ("pair", 2)):
        members = []
        for index in range(count):
            desktop = f"test.layout-{key}-{index}.desktop"
            label = f"{key.title()} {index + 1}"
            (applications / desktop).write_text(
                f"[Desktop Entry]\nType=Application\nName={label}\n"
                "Icon=utilities-terminal\nExec=/bin/true\n")
            members.append({"desktop": desktop, "label": label})
        groups[key] = dict(groups["test"], id=f"local.groups.{key}", name=key.title(), apps=members)
    settings.set_string("groups", json.dumps(groups))
    settings.set_strv("plasma-favorites", [group["id"] + ".desktop" for group in groups.values()])

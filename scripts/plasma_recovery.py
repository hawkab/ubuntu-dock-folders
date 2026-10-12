# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Remove owned panel slots and restore their recorded task manager offline."""

import json
import re
import time
from pathlib import Path


def read_record(state):
    """Read an installation record; preserve malformed records for recovery."""
    if not state.exists():
        return {}
    try:
        value = json.loads(state.read_text())
        if not isinstance(value, dict) or not isinstance(value.get("panel"), int):
            raise ValueError("The panel record must identify a panel.")
        if value.get("widget") is not None and not isinstance(value["widget"], int):
            raise ValueError("The panel record has an invalid widget ID.")
        original = value.get("original")
        if original is not None:
            if (not isinstance(original, dict) or not isinstance(original.get("id"), int)
                    or original.get("type") not in {"org.kde.plasma.icontasks", "org.kde.plasma.taskmanager"}
                    or not isinstance(original.get("configuration"), list)):
                raise ValueError("The panel record has an invalid task manager.")
            for group in original["configuration"]:
                if (not isinstance(group, dict) or not isinstance(group.get("path"), list)
                        or not all(isinstance(key, str) for key in group["path"])
                        or not isinstance(group.get("values"), dict)):
                    raise ValueError("The panel record has an invalid configuration group.")
        return value
    except (ValueError, OSError):
        state.rename(state.with_suffix(f".invalid-{time.time_ns()}.json"))
        return {}


def owned_widgets(text):
    """Map panel IDs to widget IDs whose saved plugin is Dock Folders."""
    sections = re.split(r"(?m)(?=^\[)", text)
    owned = {}
    for section in sections:
        header = section.splitlines()[0] if section else ""
        match = re.fullmatch(r"\[Containments\]\[(\d+)\]\[Applets\]\[(\d+)\]", header)
        if match and re.search(r"(?m)^plugin=io\.github\.hawkab\.DockFolders$", section):
            owned.setdefault(match[1], set()).add(match[2])
    return owned


def remove_widgets(text):
    """Return a panel config without Dock Folders slots, including unrecorded ones."""
    sections = re.split(r"(?m)(?=^\[)", text)
    owned = owned_widgets(text)
    result = []
    for section in sections:
        header = section.splitlines()[0] if section else ""
        match = re.match(r"^\[Containments\]\[(\d+)\]\[Applets\]\[(\d+)\](?:\[|$)", header)
        if match and match[2] in owned.get(match[1], set()):
            continue
        match = re.fullmatch(r"\[Containments\]\[(\d+)\]\[General\]", header)
        if match and match[1] in owned:
            section = re.sub(r"(?m)^AppletOrder=(.*)$", lambda order:
                "AppletOrder=" + ";".join(item for item in order[1].split(";")
                                          if item not in owned[match[1]]), section)
        result.append(section)
    return "".join(result)


def restore_panel(text, record):
    """Return a panel config with the owned widget replaced by its original."""
    prefix = f"[Containments][{record['panel']}][Applets]"
    own = prefix + f"[{record['widget']}]"
    sections = re.split(r"(?m)(?=^\[)", text)
    original = record.get("original")
    restored_id = str(original["id"]) if original else None
    result = []
    for section in sections:
        header = section.splitlines()[0] if section else ""
        if header == own or header.startswith(own + "["):
            continue
        if header == f"[Containments][{record['panel']}][General]":
            match = re.search(r"(?m)^AppletOrder=(.*)$", section)
            if match:
                order = match[1].split(";")
                order = [restored_id if item == str(record["widget"]) else item for item in order]
                order = [item for item in order if item]
                section = section[:match.start(1)] + ";".join(dict.fromkeys(order)) + section[match.end(1):]
        result.append(section)
    if original:
        original_prefix = prefix + f"[{original['id']}]"
        if not any(section.startswith(original_prefix + "\n") for section in result):
            result.append(original_prefix + "\nimmutability=1\nplugin=" + original["type"] + "\n\n")
            for group in original["configuration"]:
                header = original_prefix + "[Configuration]" + "".join("[" + key + "]" for key in group["path"])
                values = "".join(key + "=" + str(value) + "\n" for key, value in group["values"].items())
                result.append(header + "\n" + values + "\n")
    return "".join(result)


def recover(config, state):
    """Restore a recorded panel and remove unrecorded widgets; retain folder data."""
    config, state = Path(config), Path(state)
    had_state = state.exists()
    record = read_record(state)
    changed = False
    if config.exists():
        current = config.read_text()
        managed = str(record.get("widget")) in owned_widgets(current).get(str(record.get("panel")), set())
        restored = restore_panel(current, record) if managed else current
        restored = remove_widgets(restored)
        if current != restored:
            temporary = config.with_suffix(".dock-folders-recovery")
            temporary.write_text(restored)
            temporary.chmod(config.stat().st_mode & 0o777)
            temporary.replace(config)
            changed = True
    state.unlink(missing_ok=True)
    return changed or had_state

#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Generate settings schemas and both animation kernels from the shared contract."""

import json
import hashlib
import re
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "core"
HEADER = "// SPDX-License-Identifier: GPL-3.0-or-later\n// Copyright 2026 Grigory Olshansky\n\n"


def write_changed(path, text):
    if not path.exists() or path.read_text() != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def generate():
    """Generate runtime declarations and return the canonical contract."""
    contract = json.loads((CORE / "contract.json").read_text())
    write_changed(CORE / "contract.js", HEADER + "/** Shared preferences, effects, and adapter capabilities. */\n"
                  + "export const contract = " + json.dumps(contract, ensure_ascii=False, separators=(",", ":")) + ";\n")
    deformation = (CORE / "deform.inc").read_text()
    body = re.sub(r"^//.*\n", "", deformation, flags=re.MULTILINE)
    body = re.sub(r"\b(?:float|bool|int)\s+", "let ", body)
    body = re.sub(r"\bfloat\(", "Number(", body)
    body = re.sub(r"\bvec2\(", "point(", body)
    geometry = HEADER + "const {abs, sin, cos, min, max} = Math;\nconst point = (x, y) => ({x, y});\n"
    geometry += "const clamp = (value, low, high) => min(high, max(low, value));\nconst mix = (a, b, t) => a + (b-a)*t;\n"
    geometry += "export function smooth(low, high, value) { const t=clamp((value-low)/(high-low),0,1); return t*t*(3-2*t); }\nconst smoothstep=smooth;\n\n"
    geometry += "/** Deform a point using the shared CPU/GPU animation kernel. */\nexport function deform(position, rect, anchor, progress, edge, style) {\n"
    geometry += "    const pointX=position.x, pointY=position.y, anchorX=anchor.x, anchorY=anchor.y;\n    const rectX=rect.x, rectY=rect.y, rectWidth=rect.width, rectHeight=rect.height;\n"
    geometry += body + "}\n\n" + (CORE / "outline.js.inc").read_text()
    write_changed(CORE / "animationGeometry.js", geometry)
    write_changed(ROOT / "plasma/contents/shaders/genie.vert", (CORE / "shader.vert.in").read_text().replace("@DEFORMATION@", deformation.rstrip()))
    fading = " || ".join(f"abs(ubuf.style - {effect['id']}.0) < .5" for effect in contract["animations"] if effect["fade"])
    write_changed(ROOT / "plasma/contents/shaders/genie.frag", (CORE / "shader.frag.in").read_text().replace("@FADE_CONDITION@", "(" + fading + ")"))
    schemas(contract)
    files = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
             for file in sorted(CORE.iterdir()) if file.suffix in {".js", ".json"} and file.name != "manifest.json"}
    write_changed(CORE / "manifest.json", json.dumps({"api": contract["version"], "files": files}, indent=2) + "\n")
    return contract


def schemas(contract):
    """Write GSettings and KConfig declarations while preserving adapter-only keys."""
    path = ROOT / "extension/schemas/org.gnome.shell.extensions.dock-groups.gschema.xml"
    tree = ET.parse(path)
    schema = tree.getroot().find("schema")
    names = {preference["key"] for preference in contract["preferences"]}
    for key in list(schema):
        if key.get("name") in names:
            schema.remove(key)
    for preference in contract["preferences"]:
        type_ = {"bool": "b", "int": "i", "double": "d", "enum": "s"}[preference["type"]]
        key = ET.SubElement(schema, "key", {"name": preference["key"], "type": type_})
        default = preference.get("storageDefault", preference["default"])
        ET.SubElement(key, "default").text = repr(float(default)) if type_ == "d" else repr(default).lower() if type_ == "b" else repr(default)
        if preference["range"]:
            ET.SubElement(key, "range", {"min": str(preference.get("storageMin", min(preference["range"][0], default))), "max": str(preference["range"][1])})
        if type_ == "s":
            choices = ET.SubElement(key, "choices")
            for item in contract["animations" if preference["name"] == "animation" else "hoverEffects"]:
                ET.SubElement(choices, "choice", {"value": item["key"]})
        ET.SubElement(key, "summary").text = preference["label"]
    ET.indent(tree, space="  ")
    write_changed(path, ET.tostring(tree.getroot(), encoding="unicode", xml_declaration=True) + "\n")
    path = ROOT / "plasma/contents/config/main.xml"
    namespace = "http://www.kde.org/standards/kcfg/1.0"
    ET.register_namespace("", namespace)
    tree = ET.parse(path)
    group = tree.find("{" + namespace + "}group")
    names = {preference["name"] for preference in contract["preferences"]}
    for entry in list(group):
        if entry.get("name") in names:
            group.remove(entry)
    tag = lambda name: "{" + namespace + "}" + name
    for preference in contract["preferences"]:
        entry = ET.SubElement(group, tag("entry"), {"name": preference["name"], "type": {"bool": "Bool", "double": "Double"}.get(preference["type"], "Int")})
        default, range_ = preference.get("storageDefault", preference["default"]), preference["range"]
        if preference["type"] == "enum":
            choices = contract["animations" if preference["name"] == "animation" else "hoverEffects"]
            default = next(item["id"] for item in choices if item["key"] == default)
            range_ = [min(item["id"] for item in choices), max(item["id"] for item in choices)]
        ET.SubElement(entry, tag("default")).text = str(default).lower()
        if range_:
            ET.SubElement(entry, tag("min")).text = str(preference.get("storageMin", min(range_[0], default)))
            ET.SubElement(entry, tag("max")).text = str(range_[1])
    ET.indent(tree, space="  ")
    write_changed(path, ET.tostring(tree.getroot(), encoding="unicode", xml_declaration=True) + "\n")


def install(destination):
    """Copy the same core into a frontend bundle."""
    generate()
    shutil.copytree(ROOT / "adapters", destination.parent / "adapters", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(CORE, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.inc", "*.in", "__pycache__", "*.pyc"))


if __name__ == "__main__":
    generate()

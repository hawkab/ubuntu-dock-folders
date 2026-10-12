# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Validate shared UI strings and gettext catalogs for every desktop adapter."""

import ast
import gettext
import json
import re
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = "ubuntu-dock-folders"
SAME_WORDS = {"de": {"Name", "Transparent"}, "fr": {"Opaque", "Transparent"},
              "ro": {"Transparent"}}
LITERAL = r'''("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')'''
CALL = re.compile(r'''(?:\b_\(\s*|i18nd\(\s*["']ubuntu-dock-folders["']\s*,\s*)''' + LITERAL)
PLACEHOLDER = re.compile(r"%(?:\([^)]+\))?[sdif]")


def ui_strings(root=ROOT):
    """Return literal and contract-derived messages used by all frontends."""
    messages = {"Application folders, appearance, and animation"}
    for frontend in ("extension", "plasma", "xfce"):
        for path in (root / frontend).rglob("*"):
            if path.suffix in {".js", ".qml", ".c"}:
                messages.update(ast.literal_eval(match[1]) for match in CALL.finditer(path.read_text()))
            elif path.suffix == ".py":
                for node in ast.walk(ast.parse(path.read_text())):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id == "_" and node.args
                            and isinstance(node.args[0], ast.Constant)
                            and isinstance(node.args[0].value, str)):
                        messages.add(node.args[0].value)
    for element in ET.parse(root / "extension/preferences.ui").iter():
        if element.get("translatable") == "yes":
            messages.add(element.text)
    contract = json.loads((root / "core/contract.json").read_text())
    for collection in ("preferences", "animations", "hoverEffects"):
        messages.update(item["label"] for item in contract[collection])
    return messages


def validate(root=ROOT):
    """Reject missing, fuzzy, empty, invalid-format or unintended English translations."""
    languages = (root / "po/LINGUAS").read_text().split()
    if len(languages) != len(set(languages)) or set(languages) != {p.stem for p in (root / "po").glob("*.po")}:
        raise ValueError("LINGUAS must list every catalog exactly once")
    expected, catalogs = ui_strings(root), {}
    with tempfile.TemporaryDirectory(prefix="dock-folders-catalogs-") as directory:
        for language in languages:
            output = Path(directory) / (language + ".mo")
            try:
                subprocess.run(["msgfmt", "--check", "--check-format", str(root / "po" / (language + ".po")),
                                "-o", str(output)], check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as error:
                raise ValueError(f"Invalid catalog: {language}: {error.stderr.strip()}") from error
            with output.open("rb") as stream:
                catalogs[language] = gettext.GNUTranslations(stream)
    english = {key for key in catalogs["en"]._catalog if isinstance(key, str) and key}
    if expected - english:
        raise ValueError(f"Uncatalogued UI messages: {sorted(expected - english)}")
    for language, catalog in catalogs.items():
        messages = {key for key in catalog._catalog if isinstance(key, str) and key}
        if messages != english or catalog.info().get("language") != language:
            raise ValueError(f"Incomplete or mislabeled catalog: {language}")
        for message in messages:
            translated = catalog.gettext(message)
            if not translated.strip() or sorted(PLACEHOLDER.findall(message)) != sorted(PLACEHOLDER.findall(translated)):
                raise ValueError(f"Invalid translation: {language}: {message}")
            if language != "en" and translated == message and message not in SAME_WORDS.get(language, set()):
                raise ValueError(f"Untranslated message: {language}: {message}")
    return {"languages": len(languages), "ui_messages": len(expected), "catalog_messages": len(english)}


if __name__ == "__main__":
    print(json.dumps(validate()))

#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Build a Plasma 6 widget with its isolated folder service and translations."""

import gettext
import build_core
from localization import validate as validate_translations
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from native_build import cmake_flags

ROOT = Path(__file__).resolve().parent.parent
ID = "io.github.hawkab.DockFolders"
DOMAIN = "ubuntu-dock-folders"


def build_effects(output):
    """Compile the compositor adapter and portable Qt shader bundles."""
    native = ROOT / "build/plasma-effects"
    subprocess.run(["cmake", "-S", str(ROOT / "native/plasma-effects"), "-B", str(native),
                    "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_INSTALL_PREFIX=" + str(output), *cmake_flags()], check=True)
    subprocess.run(["cmake", "--build", str(native), "--parallel", "2"], check=True)
    subprocess.run(["cmake", "--install", str(native)], check=True)
    qsb = os.environ.get("QSB") or shutil.which("qsb") or "/usr/lib/qt6/bin/qsb"
    for source in (output / "contents/shaders").glob("genie.*"):
        if source.suffix in {".vert", ".frag"}:
            subprocess.run([qsb, "--qt6", "--qsbversion", "64", "-o", str(source) + ".qsb", str(source)], check=True)


def build():
    validate_translations()
    build_core.generate()
    output = ROOT / "build/plasma"
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / "plasma", output, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "gschemas.compiled"))
    build_core.install(output / "contents/core")
    geometry = (ROOT / "core/animationGeometry.js").read_text().replace("export function ", "function ")
    (output / "contents/ui/FolderGeometry.js").write_text(geometry)
    declarations = (ROOT / "core/contract.js").read_text().replace("export const ", "var ")
    icons = (ROOT / "core/iconGeometry.js").read_text().replace("import {contract} from './contract.js';", "").replace("export function ", "function ")
    (output / "contents/ui/IconGeometry.js").write_text(declarations + "\n" + icons)
    preferences = "\n".join((ROOT / "core" / name).read_text() for name in ("appearance.js", "preferences.js", "orbit.js", "applications.js", "settingsPreview.js", "folderInteraction.js"))
    preferences = re.sub(r"^(?:import .*|export \{.*)\n", "", preferences, flags=re.MULTILINE).replace("export function ", "function ")
    preferences=preferences.replace('miniIconLayout(', 'Geometry.miniIconLayout(')
    preferences=preferences.replace('deform(', 'AnimationGeometry.deform(')
    (output / "contents/ui/Core.js").write_text('.import "IconGeometry.js" as Geometry\n.import "FolderGeometry.js" as AnimationGeometry\n'+declarations + "\n" + preferences)
    build_effects(output)
    schema = output / "contents/schemas"
    shutil.copytree(ROOT / "extension/schemas", schema, ignore=shutil.ignore_patterns("gschemas.compiled"))
    subprocess.run(["glib-compile-schemas", "--strict", str(schema)], check=True)
    metadata = json.loads((output / "metadata.json").read_text())
    for source in sorted((ROOT / "po").glob("*.po")):
        destination = output / "contents/locale" / source.stem / "LC_MESSAGES" / f"{DOMAIN}.mo"
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["msgfmt", "--check", str(source), "-o", str(destination)], check=True)
        translate = gettext.translation(DOMAIN, str(output / "contents/locale"), [source.stem]).gettext
        metadata["KPlugin"][f"Name[{source.stem}]"] = translate("Dock folders")
        metadata["KPlugin"][f"Description[{source.stem}]"] = translate("Application folders, appearance, and animation")
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    destination = ROOT / "dist" / (ID + ".plasmoid")
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(output.rglob("*")):
            if source.is_file():
                archive.write(source, source.relative_to(output))
    print(destination)
    return output


if __name__ == "__main__":
    build()

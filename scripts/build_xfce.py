#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Build the Xfce panel plugin, shared preferences and translations."""

import shutil
import gettext
import subprocess
from pathlib import Path
import build_core
from localization import validate as validate_translations
from native_build import compiler, flags as build_flags

ROOT = Path(__file__).resolve().parent.parent


def build():
    validate_translations()
    build_core.generate()
    output = ROOT / "build/xfce"
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / "xfce", output, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.so"))
    shared = output / "shared"
    for folder in ("app", "icons", "schemas"):
        shutil.copytree(ROOT / "extension" / folder, shared / folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "gschemas.compiled"))
    shutil.copy2(ROOT / "extension/preferences.ui", shared / "preferences.ui")
    build_core.install(shared / "core")
    subprocess.run(["glib-compile-schemas", "--strict", str(shared / "schemas")], check=True)
    for source in sorted((ROOT / "po").glob("*.po")):
        target = shared / "locale" / source.stem / "LC_MESSAGES/ubuntu-dock-folders.mo"
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["msgfmt", "--check", str(source), "-o", str(target)], check=True)
    descriptor = output / "dockfolders.desktop"
    localized = descriptor.read_text()
    for source in sorted((ROOT / "po").glob("*.po")):
        translate = gettext.translation("ubuntu-dock-folders", str(shared / "locale"), [source.stem]).gettext
        localized += f"Name[{source.stem}]={translate('Dock folders')}\n"
        localized += f"Comment[{source.stem}]={translate('Application folders, appearance, and animation')}\n"
    descriptor.write_text(localized)
    from xfce_native_build import compile_plugin
    compile_plugin(output, output / "libdockfolders.so")
    flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "gdk-x11-3.0", "gdk-pixbuf-2.0", "xcomposite"], text=True).split()
    subprocess.run([*compiler(), "-shared", "-fPIC", *build_flags("CPPFLAGS"), *build_flags("CFLAGS"),
                    "-Wall", "-Wextra", "-Werror", str(output / "capture.c"), "-o", str(output / "capture.so"),
                    *flags, *build_flags("LDFLAGS")], check=True)
    print(output)
    return output


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package",action="store_true")
    options=parser.parse_args()
    output=build()
    if options.package:
        from build_xfce_package import package
        package(output)

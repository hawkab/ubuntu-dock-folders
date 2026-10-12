# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Resolve native dependencies and pin private KWin ABI versions."""

import re
import shutil
import subprocess

from desktop_payload import PLASMA_ID

BACKENDS = {"wayland": ("kwin", "libkwin6"), "x11": ("kwin-x11", "libkwin-x11-6")}
RUNTIME = ("gjs", "kpackagetool6", "python3", "python3-gi", "python3-cairo", "python3-gi-cairo", "python3-pil",
           "gir1.2-gtk-3.0", "gir1.2-gtk-4.0", "gir1.2-adw-1", "gir1.2-wnck-3.0",
           "gir1.2-libxfce4windowing-0.0", "gir1.2-gtklayershell-0.1", "grim")


def plugin_name(native):
    name = (native / "plugin-name.txt").read_text().strip()
    if not re.fullmatch(r"dockfoldersbackdrop_[a-f0-9]{12}", name):
        raise RuntimeError("Invalid companion build identity")
    return name


def pin_versions(dependencies, versions):
    for library, version in versions:
        expression = r"(?<![\w+-])" + re.escape(library) + r"\s*\([^)]*\)(?![\w+-])"
        dependencies, count = re.subn(expression, f"{library} (= {version})", dependencies)
        if count != 1:
            raise RuntimeError(f"Expected one dependency on {library}; found {count}.")
    return dependencies


def stage_companions(root, stage, multiarch):
    native, versions = [], []
    for backend, (namespace, library) in BACKENDS.items():
        name = plugin_name(root / f"build/kwin-backdrop-{backend}")
        source = root / f"build/kwinplugins-{backend}/{namespace}/effects/plugins/{name}.so"
        target = stage / f"usr/lib/{multiarch}/qt6/plugins/{namespace}/effects/plugins/{name}.so"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        native.append(target)
        version = subprocess.check_output(["dpkg-query", "-W", "-f=${Version}", library], text=True).strip()
        versions.append((library, version))
    return native, versions


def resolve(root, stage):
    multiarch = subprocess.check_output(["dpkg-architecture", "-qDEB_HOST_MULTIARCH"], text=True).strip()
    native = [stage / path for path in (
        "usr/share/gnome-shell/extensions/dock-groups@local/integration/settings-integration.so",
        f"usr/lib/{multiarch}/xfce4/panel/plugins/libdockfolders.so",
        "usr/share/ubuntu-dock-folders/xfce/capture.so",
        f"usr/share/plasma/plasmoids/{PLASMA_ID}/contents/effects/libdockfolderseffects.so",
        f"usr/share/plasma/plasmoids/{PLASMA_ID}/contents/code/dock-folders-core-runner")]
    companions, versions = stage_companions(root, stage, multiarch)
    dependencies = subprocess.check_output([
        "dpkg-shlibdeps", "-O", *["-e" + str(path) for path in native + companions]],
        cwd=root, text=True).strip().removeprefix("shlibs:Depends=")
    return pin_versions(dependencies, versions) + ", " + ", ".join(RUNTIME)

#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Build and package backdrop blur against the installed KWin backend."""

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from native_build import cmake_flags
from desktop_dependencies import BACKENDS, pin_versions, plugin_name

ROOT = Path(__file__).resolve().parent.parent


def output(*arguments):
    return subprocess.check_output(arguments, cwd=ROOT, text=True).strip()


def package(backend, native, destination, revision=1):
    """Create a backend-specific package with an exact KWin library dependency."""
    namespace, library = BACKENDS[backend]
    version = output("dpkg-query", "-W", "-f=${Version}", library)
    abi = re.search(r"\d+\.\d+\.\d+", version).group()
    release = output("dpkg-parsechangelog", "-S", "Version").split("-",1)[0] + "+kwin" + abi + f"-{revision}"
    architecture = output("dpkg", "--print-architecture")
    name = "ubuntu-dock-folders-kwin" + ("-x11" if backend == "x11" else "")
    stage = ROOT / "build" / (name + "-package")
    shutil.rmtree(stage, ignore_errors=True)
    plugins = stage / "usr/lib" / output("dpkg-architecture", "-qDEB_HOST_MULTIARCH") / "qt6/plugins" / namespace / "effects/plugins"
    plugins.mkdir(parents=True)
    plugin = plugin_name(native)
    effect = plugins / (plugin + ".so")
    shutil.copy2(native / effect.name, effect)
    subprocess.run(["strip", "--strip-unneeded", str(effect)], check=True)
    dependencies = output("dpkg-shlibdeps", "-O", "-e" + str(effect)).removeprefix("shlibs:Depends=")
    dependencies = pin_versions(dependencies, [(library, version)])
    control = stage / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        f"Package: {name}\nVersion: {release}\nArchitecture: {architecture}\n"
        "Section: kde\nPriority: optional\n"
        "Maintainer: Grigory Olshansky <hawkab@users.noreply.github.com>\n"
        f"Depends: {dependencies}\n"
        "Homepage: https://github.com/hawkab/ubuntu-dock-folders\n"
        "Description: adjustable background blur for Dock Folders in KDE Plasma\n"
        " Gaussian blur of windows behind an open folder, with a separate radius\n"
        " control. Icons and labels remain sharp. Requires the Dock Folders widget.\n"
    )
    documentation = stage / "usr/share/doc" / name
    documentation.mkdir(parents=True)
    shutil.copy2(ROOT / "debian/copyright", documentation / "copyright")
    stage.chmod(0o755)
    for entry in stage.rglob("*"):
        entry.chmod(0o755 if entry.is_dir() else 0o644)
    destination.mkdir(parents=True, exist_ok=True)
    deb = destination / f"{name}_{release}_{architecture}.deb"
    subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(stage), str(deb)], check=True)
    return deb


def build(backend, definitions, revision=1, package_result=True):
    native = ROOT / "build" / ("kwin-backdrop-" + backend)
    subprocess.run(["cmake", "-S", str(ROOT / "native/kwin-backdrop"), "-B", str(native),
                    "-DCMAKE_BUILD_TYPE=Release", "-DKWIN_BACKEND=" + backend, *cmake_flags(), *definitions], check=True)
    subprocess.run(["cmake", "--build", str(native), "--parallel", "2"], check=True)
    plugins = ROOT / "build" / ("kwinplugins-" + backend)
    shutil.rmtree(plugins, ignore_errors=True)
    subprocess.run(["cmake", "--install", str(native), "--prefix", str(plugins)], check=True)
    if package_result:
        print(package(backend, native, ROOT / "dist", revision))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("wayland", "x11"), default="wayland")
    parser.add_argument("--revision", type=int, default=1)
    parser.add_argument("--build-only", action="store_true")
    options, definitions = parser.parse_known_args()
    if options.revision < 1: parser.error("revision must be positive")
    build(options.backend, definitions, options.revision, not options.build_only)

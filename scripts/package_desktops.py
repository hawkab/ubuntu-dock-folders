#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Assemble the desktop package from validated GNOME, Plasma and Xfce builds."""

import argparse
import platform
import shutil
import subprocess

import build
import build_xfce_package
from desktop_dependencies import resolve
from desktop_payload import ROOT, install_plasma, install_dispatcher, update_catalogs, verify_builds
from package_control import combined
from package_layout import finalize


def local_version(api):
    distribution = platform.freedesktop_os_release()
    if distribution.get("ID") != "ubuntu":
        raise RuntimeError("Build this package on its target Ubuntu release.")
    return (build.VERSION.split("-", 1)[0] + "-1ubuntu" + distribution["VERSION_ID"]
            + f".1+desktops{api}")


def prepare(version, strip_native=True):
    build.package(ROOT / "build/extension", stage_only=True)
    xfce = build_xfce_package.package(ROOT / "build/xfce", stage_only=True)
    stage = ROOT / "build/package"
    shutil.copytree(xfce / "usr", stage / "usr", dirs_exist_ok=True, symlinks=True)
    shutil.rmtree(stage / "usr/share/doc/ubuntu-dock-folders-xfce")
    install_plasma(stage)
    install_dispatcher(stage)
    update_catalogs(stage)
    combined(stage / "DEBIAN/control", version, resolve(ROOT, stage))
    finalize(stage, "ubuntu-dock-folders", strip_native=strip_native)
    return stage


def assemble(stage_only=False, version=None):
    api = verify_builds()
    version = version or local_version(api)
    stage = prepare(version, strip_native=not stage_only)
    if stage_only:
        return stage
    architecture = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    destination = ROOT / f"dist/ubuntu-dock-folders_{version}_{architecture}.deb"
    destination.parent.mkdir(exist_ok=True)
    subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(stage), str(destination)], check=True)
    print(destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--version")
    options = parser.parse_args()
    assemble(options.stage_only, options.version)

#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Configure and build the Debian payload for its target Ubuntu suite."""

import argparse
import platform
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from debian.deb822 import Deb822
from package_control import description

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"noble": "gnome", "resolute": "desktops"}
DESKTOP_DEPENDENCIES = (
    "cmake", "kwin-dev", "kwin-x11-dev", "qt6-base-private-dev", "qt6-declarative-dev",
    "qt6-shader-baker", "libwayland-dev", "libkf6windowsystem-dev", "libxfce4panel-2.0-dev",
    "libxfce4ui-2-dev", "libxfce4windowing-0-dev", "libwnck-3-dev", "libgtk-layer-shell-dev",
    "libxcomposite-dev", "plasma-workspace", "plasma-desktop", "kwin-wayland", "kwin-x11", "kdialog", "kpackagetool6", "pipewire",
    "qml6-module-org-kde-kirigami", "qml6-module-org-kde-kquickcontrols", "xfce4-panel", "xfwm4",
    "xfconf", "labwc", "grim", "gir1.2-wnck-3.0", "gir1.2-libxfce4windowing-0.0",
    "gir1.2-gtklayershell-0.1",
)


def configure(root, suite, version=None):
    """Write suite-specific Debian metadata; reject unsupported suites."""
    if suite not in TARGETS:
        raise ValueError(f"Unsupported Ubuntu suite: {suite}")
    target = TARGETS[suite]
    control = root / "debian/control"
    paragraphs = list(Deb822.iter_paragraphs(control.read_text()))
    source, binary = paragraphs
    dependencies = [field.strip() for field in source["Build-Depends"].split(",")]
    dependencies = [field for field in dependencies if field.split()[0] not in DESKTOP_DEPENDENCIES]
    if target == "desktops":
        dependencies.extend(DESKTOP_DEPENDENCIES)
    source["Build-Depends"] = ",\n ".join(dependencies)
    source["Section"] = binary["Section"] = "x11" if target == "desktops" else "gnome"
    binary["Depends"] = "${shlibs:Depends}, ${misc:Depends}"
    binary["Description"] = description(target == "desktops")
    for field in ("Replaces", "Conflicts", "Provides", "Suggests"):
        binary.pop(field, None)
    if target == "desktops":
        binary.update({
            "Replaces": "ubuntu-dock-folders-xfce, ubuntu-dock-folders-kwin, ubuntu-dock-folders-kwin-x11",
            "Conflicts": "ubuntu-dock-folders-kwin, ubuntu-dock-folders-kwin-x11",
            "Provides": "ubuntu-dock-folders-xfce, ubuntu-dock-folders-kwin, ubuntu-dock-folders-kwin-x11",
            "Suggests": "gnome-shell-extension-ubuntu-dock, plasma-workspace, xfce4-panel",
        })
    control.write_text("\n".join(paragraph.dump() for paragraph in paragraphs))
    (root / "debian/build-target").write_text(target + "\n")
    set_changelog(root, suite, version)
    return target


def set_changelog(root, suite, version=None):
    """Set the source version and distribution from the release target."""
    file = root / "debian/changelog"
    text = file.read_text()
    if version is None:
        current = subprocess.check_output(["dpkg-parsechangelog", "-S", "Version"], cwd=root, text=True).strip()
        settings = tomllib.loads((root / "packaging/release.toml").read_text())
        target = next(target for target in settings["launchpad_targets"] if target["suite"] == suite)
        version = current.split("-", 1)[0] + "-" + target["version_suffix"]
    header = f"ubuntu-dock-folders ({version}) {suite};"
    text, count = re.subn(r"\Aubuntu-dock-folders \([^\n]+\) [^;\n]+;", header, text, count=1)
    if count != 1:
        raise ValueError("Source changelog has an unexpected header")
    file.write_text(text)


def selected(root=ROOT):
    target = (root / "debian/build-target").read_text().strip()
    if target not in TARGETS.values():
        raise ValueError(f"Invalid Debian build target: {target}")
    return target


def run(*command):
    subprocess.run(command, cwd=ROOT, check=True)


def build():
    import build as gnome
    extension = gnome.build()
    if selected() == "gnome":
        gnome.package(extension, stage_only=True)
        return
    import build_plasma
    import build_xfce
    import build_backdrop
    import package_desktops
    build_plasma.build()
    build_xfce.build()
    for backend in ("wayland", "x11"):
        build_backdrop.build(backend, [], package_result=False)
    version = subprocess.check_output(["dpkg-parsechangelog", "-S", "Version"], cwd=ROOT, text=True).strip()
    package_desktops.assemble(stage_only=True, version=version)


def check():
    run("make", "test")
    run("/usr/bin/python3", "scripts/test_shell.py")
    run("xvfb-run", "-a", "/usr/bin/python3", "scripts/test_shell.py", "--client-backend", "x11")
    help_text = subprocess.check_output(["gnome-shell", "--help"], text=True)
    if "--x11 " in help_text:
        run("xvfb-run", "-a", "/usr/bin/python3", "scripts/test_shell.py", "--backend", "x11")
    if selected() == "desktops":
        run("/usr/bin/python3", "scripts/test_plasma.py", "--settings")
        for backend in ("x11", "wayland"):
            ui = "--software-ui" if backend == "wayland" and not Path("/dev/dri").exists() else "--ui"
            for mode in ("--lifecycle", "--interaction", ui):
                run("/usr/bin/python3", "scripts/test_plasma_panel.py", "--backend", backend, mode)
        run("/usr/bin/python3", "scripts/test_xfce_panel.py", "--source")
        run("/usr/bin/python3", "scripts/test_xfce_wayland.py")
    for file in (ROOT / "build/package/usr/share/metainfo").glob("*.metainfo.xml"):
        run("appstreamcli", "validate", "--no-net", str(file))
    for file in (ROOT / "build/package/usr/share/applications").glob("*.desktop"):
        run("desktop-file-validate", str(file))


def install():
    destination = ROOT / "debian/ubuntu-dock-folders"
    destination.mkdir(exist_ok=True)
    for name in ("usr", "etc"):
        source = ROOT / "build/package" / name
        if source.exists():
            shutil.copytree(source, destination / name, symlinks=True, dirs_exist_ok=True)


def dependencies():
    """Preserve debhelper variables while adding the staged runtime dependencies."""
    control = Deb822((ROOT / "build/package/DEBIAN/control").read_text())
    file = ROOT / "debian/ubuntu-dock-folders.substvars"
    lines = file.read_text().splitlines() if file.exists() else []
    lines = [line for line in lines if not line.startswith("shlibs:Depends=")]
    file.write_text("\n".join(lines + ["shlibs:Depends=" + control["Depends"]]) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("configure", "build", "check", "install", "dependencies"))
    parser.add_argument("--suite", choices=TARGETS)
    parser.add_argument("--version")
    options = parser.parse_args()
    if options.command == "configure":
        suite = options.suite or platform.freedesktop_os_release().get("VERSION_CODENAME")
        if suite not in TARGETS:
            parser.error("Build on Ubuntu 24.04 or 26.04, or specify its --suite.")
        configure(ROOT, suite, options.version)
    else:
        {"build": build, "check": check, "install": install, "dependencies": dependencies}[options.command]()


if __name__ == "__main__":
    main()

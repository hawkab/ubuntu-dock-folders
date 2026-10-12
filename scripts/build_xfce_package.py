#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Package the Xfce adapter with its required core and GTK preferences."""

import shutil
import subprocess
from pathlib import Path
from package_layout import finalize
from publication_files import copy_media

ROOT = Path(__file__).resolve().parent.parent


def package(output, stage_only=False):
    stage = ROOT / "build/package-xfce"
    if stage.exists():
        shutil.rmtree(stage)
    destination = stage / "usr/share/ubuntu-dock-folders/xfce"
    shutil.copytree(output, destination, ignore=shutil.ignore_patterns(
        "*.c", "libdockfolders.so", "dockfolders.desktop", "__pycache__"))
    arch = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    multiarch = subprocess.check_output(["dpkg-architecture", "-qDEB_HOST_MULTIARCH"], text=True).strip()
    version = subprocess.check_output(["dpkg-parsechangelog", "-S", "Version"], cwd=ROOT, text=True).strip()
    library = stage / f"usr/lib/{multiarch}/xfce4/panel/plugins/libdockfolders.so"
    library.parent.mkdir(parents=True)
    shutil.copy2(output / "libdockfolders.so", library)
    descriptor = stage / "usr/share/xfce4/panel/plugins/dockfolders.desktop"
    descriptor.parent.mkdir(parents=True)
    descriptor.write_text((output / "dockfolders.desktop").read_text().replace(
        "io.github.hawkab.UbuntuDockFolders", "io.github.hawkab.DockFolders.Xfce"))
    icon = stage / "usr/share/icons/hicolor/scalable/apps/io.github.hawkab.DockFolders.Xfce.svg"
    icon.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging/io.github.hawkab.UbuntuDockFolders.svg", icon)
    management = stage / "usr/share/ubuntu-dock-folders/xfce-management"
    management.mkdir(parents=True)
    for name in ("xfce_manage.py", "backup.py", "xfce_package_lifecycle.py"):
        shutil.copy2(ROOT / "scripts" / name, management / name)
    executable = stage / "usr/bin/ubuntu-dock-folders-xfce"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        '#!/usr/bin/python3\nimport runpy,sys\n'
        'sys.path.insert(0,"/usr/share/ubuntu-dock-folders/xfce-management")\n'
        'runpy.run_path("/usr/share/ubuntu-dock-folders/xfce-management/xfce_manage.py",run_name="__main__")\n')
    docs = stage / "usr/share/doc/ubuntu-dock-folders-xfce"
    docs.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging/copyright", docs / "copyright")
    shutil.copy2(ROOT / "README.md", docs / "README.md")
    copy_media(ROOT / "docs/xfce", docs / "docs/xfce")
    control = stage / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        f"Package: ubuntu-dock-folders-xfce\nVersion: {version}\nArchitecture: {arch}\nSection: xfce\nPriority: optional\n"
        "Maintainer: Grigory Olshansky <hawkab@users.noreply.github.com>\n"
        "Depends: xfce4-panel, xfconf, gjs, python3, python3-gi, python3-cairo, python3-gi-cairo, python3-pil, gir1.2-gtk-3.0, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-wnck-3.0, gir1.2-libxfce4windowing-0.0, gir1.2-gtklayershell-0.1, grim, "
        + subprocess.check_output(["dpkg-shlibdeps", "-O", "-e"+str(library), "-e"+str(destination / "capture.so")],
                                  cwd=ROOT, text=True).strip().removeprefix("shlibs:Depends=") + "\n"
        "Homepage: https://github.com/hawkab/ubuntu-dock-folders\n"
        "Description: Application folders for the Xfce panel\n"
        " Group launchers by dragging them together, reorder applications, and\n"
        " customize each folder's appearance, background blur and animation.\n"
        " Includes the same versioned core and settings used by GNOME and Plasma.\n"
        " Selects native Wayland or X11 embedding automatically at panel startup.\n")
    (control / "prerm").write_text(
        '#!/bin/sh\nset -eu\n[ -z "${DPKG_ROOT:-}" ] || exit 0\ncase "$1" in remove|deconfigure) '
        'python3 -I /usr/share/ubuntu-dock-folders/xfce-management/xfce_package_lifecycle.py ;; esac\n')
    for path in stage.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    stage.chmod(0o755)
    executable.chmod(0o755)
    (control / "prerm").chmod(0o755)
    finalize(stage, "ubuntu-dock-folders-xfce", strip_native=not stage_only)
    if stage_only:
        return stage
    artifact = ROOT / f"dist/ubuntu-dock-folders-xfce_{version}_{arch}.deb"
    subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(stage), str(artifact)], check=True)
    print(artifact)
    return artifact

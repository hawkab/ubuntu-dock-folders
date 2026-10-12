# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Install a source plugin under a private prefix for native panel tests."""

import shutil
import subprocess


def install_source_plugin(home, source):
    multiarch = subprocess.check_output(["dpkg-architecture", "-qDEB_HOST_MULTIARCH"], text=True).strip()
    prefix = home / "prefix/usr"
    library = prefix / f"lib/{multiarch}/xfce4/panel/plugins/libdockfolders.so"
    library.parent.mkdir(parents=True)
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from xfce_native_build import compile_plugin
    compile_plugin(source, library, source / "panel.py")
    descriptor = prefix / "share/xfce4/panel/plugins/dockfolders.desktop"
    descriptor.parent.mkdir(parents=True)
    shutil.copy2(source / "dockfolders.desktop", descriptor)
    return library

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Compile the panel bridge against the distribution's Python ABI."""

import subprocess
import sysconfig
from pathlib import Path
from native_build import compiler, flags as build_flags


def compile_plugin(source, output, backend=None):
    libraries = ["libxfce4panel-2.0", "pygobject-3.0", "gmodule-2.0", "python3-embed"]
    flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", *libraries], text=True).split()
    definitions = [f'-DDOCK_FOLDERS_PYTHON_LIBRARY="{sysconfig.get_config_var("LDLIBRARY")}"']
    if backend:
        definitions.append(f'-DDOCK_FOLDERS_BACKEND="{backend}"')
    subprocess.run([*compiler(), "-shared", "-fPIC", *build_flags("CPPFLAGS"), *build_flags("CFLAGS"),
                    "-Wall", "-Wextra", "-Werror",
                    "-I" + str(Path(__file__).resolve().parent.parent / "native"),
                    *definitions, str(source / "plugin.c"), str(source / "native_controller.c"),
                    "-o", str(output), *flags, *build_flags("LDFLAGS")], check=True)

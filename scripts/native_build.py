# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Read distribution compiler flags and explicit environment overrides."""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compiler():
    return shlex.split(os.environ.get("CC", "cc"))


def flags(name):
    """Return flags for one build variable; prefer the caller's explicit value."""
    if name in os.environ:
        value = os.environ[name]
    elif shutil.which("dpkg-buildflags"):
        env = dict(os.environ)
        env.setdefault("DEB_BUILD_MAINT_OPTIONS", "hardening=+all")
        value = subprocess.check_output(["dpkg-buildflags", "--get", name], env=env, cwd=ROOT, text=True).strip()
    else:
        value = "-O2" if name in {"CFLAGS", "CXXFLAGS"} else ""
    return shlex.split(value)


def cmake_flags():
    """Pass Debian compiler and linker flags to native CMake builds."""
    link = shlex.join(flags("LDFLAGS"))
    return ["-DCMAKE_C_FLAGS:STRING=" + shlex.join(flags("CPPFLAGS") + flags("CFLAGS")),
            "-DCMAKE_CXX_FLAGS:STRING=" + shlex.join(flags("CPPFLAGS") + flags("CXXFLAGS")),
            "-DCMAKE_EXE_LINKER_FLAGS:STRING=" + link,
            "-DCMAKE_MODULE_LINKER_FLAGS:STRING=" + link,
            "-DCMAKE_SHARED_LINKER_FLAGS:STRING=" + link]

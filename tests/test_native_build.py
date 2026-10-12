# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check explicit compiler flags and CMake quoting."""

import os
import shlex
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import native_build


class NativeBuildTests(unittest.TestCase):
    def test_caller_flags_override_distribution_defaults(self):
        with patch.dict(os.environ, {"CC": "ccache gcc", "CPPFLAGS": "", "CFLAGS": "-O0 -DUSER_BUILD"}), \
                patch.object(native_build.subprocess, "check_output") as query:
            self.assertEqual(native_build.compiler(), ["ccache", "gcc"])
            self.assertEqual(native_build.flags("CFLAGS"), ["-O0", "-DUSER_BUILD"])
            self.assertEqual(native_build.flags("CPPFLAGS"), [])
            query.assert_not_called()

    def test_cmake_flags_preserve_arguments_containing_spaces(self):
        values = {"CPPFLAGS": "-D_FORTIFY_SOURCE=3", "CFLAGS": "-O2",
                  "CXXFLAGS": "'-ffile-prefix-map=/tmp/source tree=.' -O2",
                  "LDFLAGS": "-Wl,-z,now"}
        with patch.dict(os.environ, values):
            options = native_build.cmake_flags()
        cxx = next(value.split("=", 1)[1] for value in options if value.startswith("-DCMAKE_CXX_FLAGS:"))
        self.assertEqual(shlex.split(cxx), ["-D_FORTIFY_SOURCE=3", "-ffile-prefix-map=/tmp/source tree=.", "-O2"])

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check staged binary relocation and Debian checksums without installing files."""

import ctypes
import gzip
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from package_layout import finalize


class PackageLayoutTests(unittest.TestCase):
    def test_debian_staging_retains_debug_symbols_until_debhelper_strips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            (root / "debian").mkdir()
            (root / "debian/changelog").write_text("Changelog\n")
            (stage / "DEBIAN").mkdir(parents=True)
            installed = stage / "usr/share/example/module.so"
            installed.parent.mkdir(parents=True)
            code = root / "module.c"
            code.write_text("int answer(void) { return 42; }\n")
            subprocess.run(["cc", "-g", "-shared", "-fPIC", str(code), "-o", str(installed)],
                           check=True, capture_output=True)
            original = installed.read_bytes()
            finalize(stage, "example", root=root, strip_native=False)
            self.assertEqual(installed.read_bytes(), original)

    def test_native_files_load_through_relative_links_and_build_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            (root / "debian").mkdir()
            (root / "debian/changelog").write_text("Review package changelog\n")
            (stage / "DEBIAN").mkdir(parents=True)
            (stage / "DEBIAN/control").write_text("Package: example\nInstalled-Size: 1\nDescription: Test\n")
            module = root / "module.so"
            code = root / "module.c"
            code.write_text("int answer(void) { return 42; }\n")
            subprocess.run(["cc", "-g", "-shared", "-fPIC", str(code), "-o", str(module)],
                           check=True, capture_output=True)
            original = module.read_bytes()
            installed = stage / "usr/share/example/module.so"
            installed.parent.mkdir(parents=True)
            shutil.copy2(module, installed)
            unrelated = stage / "usr/share/example/settings.json"
            unrelated.write_text("{}\n")
            unrelated.chmod(0o664)
            installed.parent.chmod(0o775)
            finalize(stage, "example", root=root)
            self.assertEqual(module.read_bytes(), original)
            self.assertTrue(installed.is_symlink())
            self.assertTrue(installed.resolve().is_relative_to(stage / "usr/lib"))
            self.assertFalse(Path(installed.readlink()).is_absolute())
            self.assertEqual(ctypes.CDLL(str(installed)).answer(), 42)
            self.assertLess(installed.stat().st_size, len(original))
            self.assertEqual(unrelated.stat().st_mode & 0o777, 0o644)
            self.assertEqual(installed.parent.stat().st_mode & 0o777, 0o755)
            self.assertEqual(gzip.decompress((stage / "usr/share/doc/example/changelog.Debian.gz").read_bytes()),
                             b"Review package changelog\n")
            checksums = (stage / "DEBIAN/md5sums").read_text().splitlines()
            self.assertFalse(any(line.endswith("usr/share/example/module.so") for line in checksums))
            for line in checksums:
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.md5((stage / name).read_bytes()).hexdigest(), digest)
            self.assertNotIn("Installed-Size: 1\n", (stage / "DEBIAN/control").read_text())

    def test_configuration_files_are_excluded_from_package_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            (root / "debian").mkdir()
            (root / "debian/changelog").write_text("Changelog\n")
            (stage / "DEBIAN").mkdir(parents=True)
            (stage / "DEBIAN/conffiles").write_text("/etc/example.conf\n")
            (stage / "etc").mkdir()
            (stage / "etc/example.conf").write_text("user-editable\n")
            finalize(stage, "example", root=root)
            self.assertNotIn("etc/example.conf", (stage / "DEBIAN/md5sums").read_text())

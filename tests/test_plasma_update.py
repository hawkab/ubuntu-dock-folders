# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Keep already-mapped translation catalogs intact during widget updates."""

import mmap
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_manage as manager


class PlasmaUpdateTests(unittest.TestCase):
    def test_update_waits_for_the_panel_to_be_created(self):
        import plasma_update
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "installed"
            installed.mkdir()
            saved = root / "backup"
            saved.mkdir()
            panel = {"id": 2, "order": "3;4;30;6", "height": 46}
            snapshots = iter([[], [panel]])
            fake = SimpleNamespace(ROOT=root, GLib=manager.GLib, stop_helper=lambda: None,
                                   package_path=lambda: root / "build/plasma",
                                   write_service=lambda package: None,
                                   install_locales=lambda package: None,
                                   snapshot=lambda: next(snapshots))
            with patch.object(plasma_update.subprocess, "run"), patch.object(plasma_update.time, "sleep") as retry:
                plasma_update.refresh(fake, saved, panel, installed)
            retry.assert_called_once_with(.1)

    def test_translation_update_keeps_the_mapped_catalog_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = b"old translation catalog" * 100
            new = b"new" * 2000
            package = root / "package"
            source = package / "contents/locale/ru/LC_MESSAGES/ubuntu-dock-folders.mo"
            source.parent.mkdir(parents=True)
            source.write_bytes(new)
            target = root / "data/locale/ru/LC_MESSAGES/ubuntu-dock-folders.mo"
            target.parent.mkdir(parents=True)
            target.write_bytes(old)
            inode = target.stat().st_ino
            with target.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as catalog:
                with patch.object(manager, "DATA", root / "data"):
                    manager.install_locales(package)
                self.assertEqual(catalog[:], old)
            self.assertEqual(target.read_bytes(), new)
            self.assertNotEqual(target.stat().st_ino, inode)

    def test_shell_stops_before_upgrade_and_starts_after_rollback(self):
        import subprocess
        from types import SimpleNamespace
        import plasma_update

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "installed"
            installed.mkdir()
            (installed / "metadata.json").write_text("{}")
            saved = root / "backup"
            saved.mkdir()
            calls = []

            def run(command, **kwargs):
                calls.append(command)
                if command[0] == "kpackagetool6" and command[-1] == str(root / "build/plasma"):
                    raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0)

            fake = SimpleNamespace(ROOT=root, stop_helper=lambda: calls.append(["helper", "stop"]),
                                   package_path=lambda: root / "build/plasma",
                                   write_service=lambda package: None,
                                   install_locales=lambda package: calls.append(["locales", str(package)]))
            with patch.object(plasma_update.subprocess, "run", side_effect=run):
                with self.assertRaises(subprocess.CalledProcessError):
                    plasma_update.refresh(fake, saved, {"id": 2}, installed)
            self.assertEqual(calls[0], ["systemctl", "--user", "stop", plasma_update.UNIT])
            self.assertEqual(calls[3][-1], str(saved / "plasma-widget"))
            self.assertEqual(calls[-1], ["systemctl", "--user", "start", plasma_update.UNIT])
            self.assertTrue((saved / "plasma-widget/metadata.json").exists())

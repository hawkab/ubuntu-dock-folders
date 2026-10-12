# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Keep local notes out of binary packages and published source snapshots."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import release_context
from publication_files import copy_media


class PublicationFilesTests(unittest.TestCase):
    def test_media_copy_excludes_notes_and_preserves_asset_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "docs", root / "package"
            (source / "plasma").mkdir(parents=True)
            (source / "plasma/screen.png").write_bytes(b"image fixture")
            (source / "demo.webm").write_bytes(b"video fixture")
            for name in ("review.md", "notes.txt", "session.log", "settings.json", "support.html"):
                (source / name).write_text("local material\n")
            copy_media(source, destination)
            self.assertEqual(sorted(str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()),
                             ["demo.webm", "plasma/screen.png"])
            self.assertEqual((destination / "plasma/screen.png").read_bytes(), b"image fixture")

    def test_media_copy_rejects_links_outside_documentation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "docs"
            source.mkdir()
            (root / "private.png").write_bytes(b"private")
            (source / "screen.png").symlink_to("../private.png")
            with self.assertRaisesRegex(ValueError, "source directory"):
                copy_media(source, root / "package")

    def test_package_contains_no_extra_markdown_or_local_notes(self):
        documentation = ROOT / "build/package/usr/share/doc/ubuntu-dock-folders"
        self.assertTrue(documentation.is_dir())
        markdown = sorted(str(path.relative_to(documentation)) for path in documentation.rglob("*")
                          if path.is_file() and path.suffix.lower() in {".md", ".markdown"})
        self.assertEqual(markdown, ["README.md"])
        for path in (documentation / "docs").rglob("*"):
            if path.is_file():
                self.assertIn(path.suffix.lower(), {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm"})

    def test_source_snapshot_excludes_even_tracked_local_materials(self):
        public = ["README.md", "core/contract.json", "docs/screen.png", "native/CMakeLists.txt", "provenance/signer.asc"]
        private = ["docs/review.md", "docs/development.md", "provenance/README.md", "notes.md",
                   "reports/result.json", "outputs/screen.png", "backups/settings.json", "build/compiler.log"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in public + private:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture\n")
            with patch.object(release_context, "ROOT", root), patch.object(
                    release_context, "run", return_value="\0".join(public + private) + "\0"):
                self.assertEqual(release_context.source_files(), sorted(public))


if __name__ == "__main__":
    unittest.main()

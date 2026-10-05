# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check immutable artifacts and authenticated release manifests."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apt_repo
import release


class ReleaseTests(unittest.TestCase):
    """Reject changed files, unexpected assets and unsafe manifest paths."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.home = Path(cls.temporary.name) / "gnupg"
        cls.home.mkdir(mode=0o700)
        cls.env = os.environ | {"GNUPGHOME": str(cls.home)}
        subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                "Release test <test@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env=cls.env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        keys = subprocess.check_output(
            ["gpg", "--with-colons", "--list-keys"], env=cls.env, text=True
        )
        cls.fingerprint = next(
            line.split(":")[9] for line in keys.splitlines() if line.startswith("fpr:")
        )

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["gpgconf", "--kill", "all"], env=cls.env, check=True)
        cls.temporary.cleanup()

    def manifest(self, directory, extra=None):
        settings = {
            "suite": "noble",
            "architecture": "amd64",
            "signing_fingerprint": self.fingerprint,
        }
        (directory / "package.deb").write_bytes(b"package content")
        (directory / "source_source.changes").write_bytes(b"source")
        manifest = {
            "suite": "noble",
            "architecture": "amd64",
            "files": {p.name: apt_repo.sha256(p) for p in directory.iterdir()},
        }
        (directory / "release.json").write_text(json.dumps(manifest))
        sums = "".join(f"{apt_repo.sha256(p)}  {p.name}\n" for p in directory.iterdir())
        (directory / "SHA256SUMS").write_text(sums + (extra or ""))
        subprocess.run(
            ["gpg", "--batch", "--armor", "--detach-sign", str(directory / "SHA256SUMS")],
            env=self.env,
            check=True,
        )
        return settings

    def test_immutable_package_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, published = root / "source", root / "published"
            source.write_bytes(b"first")
            apt_repo.immutable_copy(source, published)
            apt_repo.immutable_copy(source, published)
            source.write_bytes(b"replaced")
            with self.assertRaisesRegex(ValueError, "cannot be replaced"):
                apt_repo.immutable_copy(source, published)
            self.assertEqual(published.read_bytes(), b"first")

    def test_modified_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self.manifest(root)
            (root / "package.deb").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release.verify_release(root, settings, self.env)

    def test_unlisted_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self.manifest(root)
            (root / "unexpected").write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "Unexpected release artifacts"):
                release.verify_release(root, settings, self.env)

    def test_parent_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self.manifest(root, "0" * 64 + "  ../outside\n")
            with self.assertRaisesRegex(ValueError, "Invalid checksum manifest"):
                release.verify_release(root, settings, self.env)

    def test_valid_signature_with_wrong_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self.manifest(root)
            settings["signing_fingerprint"] = "0" * 40
            with self.assertRaisesRegex(ValueError, "unexpected signing key"):
                release.verify_release(root, settings, self.env)

    def test_private_and_ignored_files_are_not_in_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", root], check=True)
            (root / ".gitignore").write_text("secret.asc\nbuild/\n")
            (root / "public").write_text("source")
            (root / "secret.asc").write_text("private")
            (root / "build").mkdir()
            (root / "build/artifact").write_text("binary")
            with patch.object(release, "ROOT", root):
                self.assertEqual(release.source_files(), [".gitignore", "public"])

    def test_successful_source_build_waits_for_binary_publication(self):
        source = {"self_link": "https://example.invalid/source", "source_package_version": "1.0.3"}
        settings = {"suite": "noble", "architecture": "amd64"}
        binary = {
            "status": "Pending",
            "binary_package_name": release.PACKAGE,
            "binary_package_version": "1.0.3",
            "distro_arch_series_link": "https://api.launchpad.net/1.0/ubuntu/noble/amd64",
        }
        for entries, expected in (
            ([], False),
            ([binary], False),
            ([binary | {"status": "Published"}], True),
            ([binary | {"status": "Published", "distro_arch_series_link": "/noble/arm64"}], False),
        ):
            with self.subTest(entries=entries):
                with patch.object(release, "launchpad_json", return_value={"entries": entries}):
                    self.assertEqual(release.launchpad_binary_published(source, settings), expected)

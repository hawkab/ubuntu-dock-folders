# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check immutable artifacts and authenticated release manifests."""

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apt_repo
import release
import release_context
import release_artifacts
import launchpad_publish


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

    def test_current_apt_index_excludes_retained_old_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            pool = archive / "pool/main/u/ubuntu-dock-folders"
            packages = []
            for version in ("1.0", "2.0"):
                stage = root / version
                (stage / "DEBIAN").mkdir(parents=True)
                (stage / "DEBIAN/control").write_text(
                    "Package: ubuntu-dock-folders\n"
                    f"Version: {version}\nArchitecture: amd64\n"
                    "Maintainer: Example <test@example.invalid>\n"
                    "Description: Archive retention test\n"
                )
                deb = root / f"ubuntu-dock-folders_{version}_amd64.deb"
                subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(stage), str(deb)],
                               check=True, stdout=subprocess.DEVNULL)
                packages.append(deb)
            apt_repo.immutable_copy(packages[0], pool / packages[0].name)
            settings = {
                "suite": "noble", "architecture": "amd64",
                "apt_url": "https://example.invalid/apt/",
                "signing_fingerprint": self.fingerprint,
            }
            def compose(deb, output, config):
                (output / "Components-amd64.yml").write_text("---\n")

            with (
                patch.object(apt_repo, "compose", side_effect=compose),
                patch.object(apt_repo, "verify_archive"),
            ):
                apt_repo.update_archive(packages[1], archive, settings, self.env)
            index = (archive / "dists/noble/main/binary-amd64/Packages").read_text()
            self.assertIn("Version: 2.0\n", index)
            self.assertNotIn("Version: 1.0\n", index)
            for deb in packages:
                self.assertEqual((pool / deb.name).read_bytes(), deb.read_bytes())

    def test_modified_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self.manifest(root)
            (root / "package.deb").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release_artifacts.verify_release(root, settings, self.env)

    def test_unlisted_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self.manifest(root)
            (root / "unexpected").write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "Unexpected release artifacts"):
                release_artifacts.verify_release(root, settings, self.env)

    def test_parent_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self.manifest(root, "0" * 64 + "  ../outside\n")
            with self.assertRaisesRegex(ValueError, "Invalid checksum manifest"):
                release_artifacts.verify_release(root, settings, self.env)

    def test_valid_signature_with_wrong_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self.manifest(root)
            settings["signing_fingerprint"] = "0" * 40
            with self.assertRaisesRegex(ValueError, "unexpected signing key"):
                release_artifacts.verify_release(root, settings, self.env)

    def test_private_and_ignored_files_are_not_in_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", root], check=True)
            (root / ".gitignore").write_text("secret.asc\nbuild/\n")
            (root / "public").write_text("source")
            (root / "secret.asc").write_text("private")
            (root / "build").mkdir()
            (root / "build/artifact").write_text("binary")
            with patch.object(release_context, "ROOT", root):
                self.assertEqual(release_context.source_files(), [".gitignore", "public"])

    def test_archive_uses_assets_from_the_selected_source_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "reviewed"
            (source / "packaging").mkdir(parents=True)
            (source / "packaging/archive-key.asc").write_text("reviewed public key")
            (source / "packaging/apt-index.html").write_text("reviewed archive page")
            package = root / "package.deb"
            package.write_bytes(b"package")
            archive = root / "archive"
            settings = {"suite": "noble", "architecture": "amd64",
                        "apt_url": "https://example.invalid/apt/", "signing_fingerprint": "test"}

            def compose(deb, output, config):
                (output / "Components-amd64.yml").write_text("---\n")

            with patch.object(apt_repo, "run", return_value=""), patch.object(
                    apt_repo, "compose", side_effect=compose), patch.object(apt_repo, "verify_archive"):
                apt_repo.update_archive(package, archive, settings, source_root=source)
            self.assertEqual((archive / "archive-key.asc").read_text(), "reviewed public key")
            self.assertEqual((archive / "index.html").read_text(), "reviewed archive page")

    def test_changelog_uses_the_requested_source_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "debian").mkdir()
            (root / "debian/changelog").write_text(
                "ubuntu-dock-folders (9.8.7-1ubuntu24.04.1) noble; urgency=medium\n\n"
                "  * Source checkout fixture.\n\n"
                " -- Example Author <example@example.invalid>  Mon, 05 Oct 2026 12:00:00 +0000\n"
            )
            with patch.object(release_context, "ROOT", root):
                self.assertEqual(release_context.changelog("Version"), "9.8.7-1ubuntu24.04.1")

    def test_snapshot_preserves_shared_core_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            target = Path(directory) / "snapshot"
            (root / "extension").mkdir(parents=True)
            (root / "core").mkdir()
            (root / "core/api.js").write_text("export const api = 9;\n")
            (root / "extension/core").symlink_to("../core")
            with patch.object(release_context, "ROOT", root), patch.object(
                    release_context, "source_files", return_value=["core/api.js", "extension/core"]):
                release_context.snapshot(target)
            self.assertTrue((target / "extension/core").is_symlink())
            self.assertEqual((target / "extension/core/api.js").read_text(), "export const api = 9;\n")

    def test_snapshot_rejects_external_and_missing_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            outside = Path(directory) / "private"
            outside.write_text("private data")
            link = root / "link"
            for destination in ("../private", "missing", str(outside)):
                with self.subTest(destination=destination):
                    link.symlink_to(destination)
                    with patch.object(release_context, "ROOT", root), patch.object(
                            release_context, "source_files", return_value=["link"]):
                        with self.assertRaisesRegex(ValueError, "checkout|relative target"):
                            release_context.snapshot(Path(directory) / "snapshot")
                    link.unlink()

    def test_series_have_distinct_versions_and_include_the_common_binary(self):
        settings = {"suite": "noble", "launchpad_targets": [
            {"suite": "noble", "version_suffix": "1ubuntu24.04.1"},
            {"suite": "resolute", "version_suffix": "1ubuntu26.04.1"},
        ]}
        self.assertEqual(release_context.launchpad_targets(settings, "9.8.7-1ubuntu24.04.1"), [
            {"suite": "noble", "version": "9.8.7-1ubuntu24.04.1"},
            {"suite": "resolute", "version": "9.8.7-1ubuntu26.04.1"},
        ])
        with self.assertRaisesRegex(ValueError, "include the release binary"):
            release_context.launchpad_targets(settings, "9.8.7-2ubuntu24.04.1")
        settings["launchpad_targets"][1]["version_suffix"] = "1ubuntu24.04.1"
        with self.assertRaisesRegex(ValueError, "distinct source versions"):
            release_context.launchpad_targets(settings, "9.8.7-1ubuntu24.04.1")

    def test_native_release_binary_requires_its_target_ubuntu_series(self):
        with patch.object(release_context.platform, "freedesktop_os_release", return_value={
                "ID": "ubuntu", "VERSION_CODENAME": "resolute"}):
            release_context.validate_build_series({"suite": "resolute"})
            with self.assertRaisesRegex(ValueError, "noble binary.*Ubuntu noble"):
                release_context.validate_build_series({"suite": "noble"})
        with patch.object(release_context.platform, "freedesktop_os_release", return_value={
                "ID": "debian", "VERSION_CODENAME": "noble"}):
            with self.assertRaisesRegex(ValueError, "native library dependencies"):
                release_context.validate_build_series({"suite": "noble"})

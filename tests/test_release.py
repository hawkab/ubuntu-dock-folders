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

    def test_changelog_uses_the_requested_source_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "debian").mkdir()
            (root / "debian/changelog").write_text(
                "ubuntu-dock-folders (9.8.7-1ubuntu24.04.1) noble; urgency=medium\n\n"
                "  * Source checkout fixture.\n\n"
                " -- Example Author <example@example.invalid>  Mon, 05 Oct 2026 12:00:00 +0000\n"
            )
            with patch.object(release, "ROOT", root):
                self.assertEqual(release.changelog("Version"), "9.8.7-1ubuntu24.04.1")

    def test_series_have_distinct_versions_and_include_the_common_binary(self):
        settings = {"suite": "noble", "launchpad_targets": [
            {"suite": "noble", "version_suffix": "1ubuntu24.04.1"},
            {"suite": "resolute", "version_suffix": "1ubuntu26.04.1"},
        ]}
        self.assertEqual(release.launchpad_targets(settings, "9.8.7-1ubuntu24.04.1"), [
            {"suite": "noble", "version": "9.8.7-1ubuntu24.04.1"},
            {"suite": "resolute", "version": "9.8.7-1ubuntu26.04.1"},
        ])
        with self.assertRaisesRegex(ValueError, "include the release binary"):
            release.launchpad_targets(settings, "9.8.7-2ubuntu24.04.1")
        settings["launchpad_targets"][1]["version_suffix"] = "1ubuntu24.04.1"
        with self.assertRaisesRegex(ValueError, "distinct source versions"):
            release.launchpad_targets(settings, "9.8.7-1ubuntu24.04.1")

    def test_resume_uploads_only_the_missing_series(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            version = "9.8.7-1ubuntu24.04.1"
            uploads = [{
                "suite": suite,
                "version": f"9.8.7-1ubuntu{ubuntu}.1",
                "changes": f"ubuntu-dock-folders_9.8.7-1ubuntu{ubuntu}.1_source.changes",
            } for suite, ubuntu in (("noble", "24.04"), ("resolute", "26.04"))]
            manifest = {"suite": "noble", "version": version, "upstream": "9.8.7", "launchpad": uploads}
            settings = {"launchpad_transport": "ftp", "launchpad_owner": "example", "launchpad_archive": "folders"}
            payload = root / "source.tar.xz"
            payload.write_bytes(b"source")
            for upload in uploads:
                (root / upload["changes"]).write_text("signed source fixture")
            text = f"Checksums-Sha256:\n {apt_repo.sha256(payload)} {payload.stat().st_size} {payload.name}\n\n"

            def sources(target, requested, status=None):
                return [{}] if target["suite"] == "noble" and status == "Pending" else []

            with (
                patch.object(release, "launchpad_sources", side_effect=sources),
                patch.object(release, "run", return_value=text) as run,
            ):
                release.upload_launchpad(root, manifest, settings, {})
            uploads_sent = [call.args for call in run.call_args_list if call.args[0] == "dput"]
            self.assertEqual(len(uploads_sent), 1)
            self.assertEqual(uploads_sent[0][-1], root / uploads[1]["changes"])

    def test_pending_source_build_is_tracked_before_publication(self):
        now = [0]
        settings = {"suite": "noble", "architecture": "amd64"}
        source = {"self_link": "https://example.invalid/source", "source_package_version": "9.8.7"}
        binary = {
            "binary_package_name": release.PACKAGE,
            "binary_package_version": "9.8.7",
            "distro_arch_series_link": "https://api.launchpad.net/1.0/ubuntu/noble/amd64",
        }

        def sources(target, version, status=None):
            published = now[0] >= 90
            if (status == "Pending") == published:
                return []
            return [source | {"status": "Published" if published else "Pending"}]

        def response(url):
            if url.endswith("getBuilds"):
                return {"entries": [{"buildstate": "Currently building" if now[0] < 30 else "Successfully built"}]}
            if now[0] < 60:
                return {"entries": []}
            return {"entries": [binary | {"status": "Published" if now[0] >= 90 else "Pending"}]}

        def sleep(seconds):
            now[0] += seconds

        with (
            patch.object(release, "launchpad_sources", side_effect=sources),
            patch.object(release, "launchpad_json", side_effect=response),
            patch.object(release.time, "monotonic", side_effect=lambda: now[0]),
            patch.object(release.time, "sleep", side_effect=sleep),
        ):
            release.wait_launchpad(settings, "9.8.7", 60)
        self.assertEqual(now[0], 90)

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

    def test_launchpad_progress_renews_stage_timeout(self):
        now = [0]
        source = {"self_link": "https://example.invalid/source", "status": "Published", "source_package_version": "1.0.4"}
        settings = {"suite": "noble", "architecture": "amd64"}
        binary = {
            "binary_package_name": release.PACKAGE,
            "binary_package_version": "1.0.4",
            "distro_arch_series_link": "https://api.launchpad.net/1.0/ubuntu/noble/amd64",
        }

        def response(url):
            if url.endswith("getBuilds"):
                state = "Currently building" if now[0] < 30 else "Successfully built"
                return {"entries": [{"buildstate": state}]}
            if now[0] < 60:
                return {"entries": []}
            status = "Pending" if now[0] < 90 else "Published"
            return {"entries": [binary | {"status": status}]}

        def sleep(seconds):
            now[0] += seconds

        with (
            patch.object(release, "launchpad_sources", return_value=[source]),
            patch.object(release, "launchpad_json", side_effect=response),
            patch.object(release.time, "monotonic", side_effect=lambda: now[0]),
            patch.object(release.time, "sleep", side_effect=sleep),
        ):
            release.wait_launchpad(settings, "1.0.4", 60)
        self.assertEqual(now[0], 90)

    def test_launchpad_stalled_stage_still_times_out(self):
        now = [0]
        source = {"self_link": "https://example.invalid/source", "status": "Published", "source_package_version": "1.0.4"}

        def sleep(seconds):
            now[0] += seconds

        with (
            patch.object(release, "launchpad_sources", return_value=[source]),
            patch.object(release, "launchpad_json", return_value={"entries": [{"buildstate": "Currently building"}]}),
            patch.object(release.time, "monotonic", side_effect=lambda: now[0]),
            patch.object(release.time, "sleep", side_effect=sleep),
        ):
            with self.assertRaisesRegex(ValueError, "Launchpad build pending"):
                release.wait_launchpad({}, "1.0.4", 60)
        self.assertEqual(now[0], 60)

    def test_launchpad_build_failure_is_reported_immediately(self):
        with (
            patch.object(release, "launchpad_sources", return_value=[{"self_link": "https://example.invalid/source"}]),
            patch.object(release, "launchpad_json", return_value={"entries": [{"buildstate": "Failed to build"}]}),
            patch.object(release.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(ValueError, "Failed to build"):
                release.wait_launchpad({}, "1.0.4", 60)
        sleep.assert_not_called()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check immutable artifacts and authenticated release manifests."""

import json
import io
import os
import subprocess
import sys
import tempfile
import urllib.error
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


class LaunchpadPublishTests(unittest.TestCase):
    def test_api_retries_transient_failures(self):
        url = "https://example.invalid/source"
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"entries": []}')
        failures = [TimeoutError("read timed out"),
                    urllib.error.HTTPError(url, 503, "Unavailable", {}, None)]
        with (
            patch.object(launchpad_publish.urllib.request, "urlopen",
                         side_effect=[*failures, response]) as request,
            patch.object(launchpad_publish.time, "sleep") as sleep,
        ):
            self.assertEqual(launchpad_publish.launchpad_json(url), {"entries": []})
        self.assertEqual(request.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10])

    def test_api_network_retries_are_bounded(self):
        for error in (TimeoutError("read timed out"), urllib.error.URLError("connection reset")):
            with (
                self.subTest(error=error),
                patch.object(launchpad_publish.urllib.request, "urlopen", side_effect=error) as request,
                patch.object(launchpad_publish.time, "sleep") as sleep,
            ):
                with self.assertRaises(type(error)):
                    launchpad_publish.launchpad_json("https://example.invalid/source")
            self.assertEqual(request.call_count, 3)
            self.assertEqual(sleep.call_count, 2)

    def test_api_permanent_http_errors_fail_without_retry(self):
        for status in (400, 401, 403, 404):
            error = urllib.error.HTTPError("https://example.invalid/source", status, "Rejected", {}, None)
            self.addCleanup(error.close)
            with (
                self.subTest(status=status),
                patch.object(launchpad_publish.urllib.request, "urlopen", side_effect=error) as request,
                patch.object(launchpad_publish.time, "sleep") as sleep,
            ):
                with self.assertRaises(urllib.error.HTTPError):
                    launchpad_publish.launchpad_json(error.url)
            request.assert_called_once()
            sleep.assert_not_called()

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
                patch.dict(os.environ, {"LAUNCHPAD_UPLOAD_TRANSPORT": "ftp"}),
                patch.object(launchpad_publish, "launchpad_sources", side_effect=sources),
                patch.object(launchpad_publish, "run", return_value=text) as run,
            ):
                launchpad_publish.upload_launchpad(root, manifest, settings, {})
            uploads_sent = [call.args for call in run.call_args_list if call.args[0] == "dput"]
            self.assertEqual(len(uploads_sent), 1)
            self.assertEqual(uploads_sent[0][-1], root / uploads[1]["changes"])


    def test_pending_source_build_is_tracked_before_publication(self):
        now = [0]
        settings = {"suite": "noble", "architecture": "amd64"}
        source = {"self_link": "https://example.invalid/source", "source_package_version": "9.8.7"}
        binary = {
            "binary_package_name": release_context.PACKAGE,
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
            patch.object(launchpad_publish, "launchpad_sources", side_effect=sources),
            patch.object(launchpad_publish, "launchpad_json", side_effect=response),
            patch.object(launchpad_publish.time, "sleep", side_effect=sleep),
        ):
            launchpad_publish.wait_launchpad(settings, "9.8.7")
        self.assertEqual(now[0], 90)


    def test_upload_retries_server_errors_but_rejects_permanent_errors(self):
        for message, failures, attempts, success in (
            ("550 Requested action not taken: internal server error\n", 1, 2, True),
            ("550 Requested action not taken: internal server error\n", 3, 3, False),
            ("Invalid signature\n", 1, 1, False),
        ):
            with self.subTest(message=message, failures=failures), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                payload = root / "source.tar.xz"
                payload.write_bytes(b"source")
                upload = {"suite": "resolute", "version": "9.8.7", "changes": "source.changes"}
                (root / upload["changes"]).write_text("signed source fixture")
                text = f"Checksums-Sha256:\n {apt_repo.sha256(payload)} {payload.stat().st_size} {payload.name}\n\n"
                settings = {"launchpad_transport": "ftp", "launchpad_owner": "example", "launchpad_archive": "folders"}
                responses = [text] + [subprocess.CalledProcessError(1, "dput", output=message)] * failures
                if success:
                    responses.append("Successfully uploaded packages.\n")
                with (
                    patch.dict(os.environ, {"LAUNCHPAD_UPLOAD_TRANSPORT": "ftp"}),
                    patch.object(launchpad_publish, "launchpad_sources", return_value=[]),
                    patch.object(launchpad_publish, "run", side_effect=responses) as run,
                    patch.object(launchpad_publish.time, "sleep") as sleep,
                ):
                    if success:
                        launchpad_publish.upload_launchpad_source(root, upload, settings, {})
                    else:
                        with self.assertRaises(subprocess.CalledProcessError):
                            launchpad_publish.upload_launchpad_source(root, upload, settings, {})
                self.assertEqual(len([c for c in run.call_args_list if c.args[0] == "dput"]), attempts)
                self.assertEqual(sleep.call_count, attempts - 1)


    def test_sftp_writes_to_virtual_paths_without_stat_or_directory_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = [root / "source.dsc", root / "source.tar.xz", root / "source.changes"]
            for file in files:
                file.write_bytes(file.name.encode())
            identity = root / "upload-key"
            settings = {"launchpad_owner": "example", "launchpad_archive": "folders"}
            paramiko = MagicMock()
            client = paramiko.SSHClient.return_value.__enter__.return_value
            remote = client.open_sftp.return_value.__enter__.return_value
            sent = []

            @contextmanager
            def write(path, mode):
                self.assertEqual(mode, "wb")
                data = io.BytesIO()
                yield data
                sent.append((path, data.getvalue()))

            remote.open.side_effect = write
            with patch.dict(sys.modules, {"paramiko": paramiko}):
                launchpad_publish.upload_sftp(files, settings, identity)
            self.assertEqual(sent, [(f"~example/ubuntu/folders/{f.name}", f.read_bytes()) for f in files])
            client.load_host_keys.assert_called_once_with(str(release_context.ROOT / "packaging/launchpad-known-hosts"))
            client.set_missing_host_key_policy.assert_called_once_with(paramiko.RejectPolicy.return_value)
            client.connect.assert_called_once_with(
                "ppa.launchpad.net", username="example", key_filename=str(identity),
                allow_agent=False, look_for_keys=False, timeout=15, auth_timeout=15, banner_timeout=15,
            )
            remote.chdir.assert_not_called()
            remote.stat.assert_not_called()
            remote.rename.assert_not_called()


    def test_successful_source_build_waits_for_binary_publication(self):
        source = {"self_link": "https://example.invalid/source", "source_package_version": "1.0.3"}
        settings = {"suite": "noble", "architecture": "amd64"}
        binary = {
            "status": "Pending",
            "binary_package_name": release_context.PACKAGE,
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
                with patch.object(launchpad_publish, "launchpad_json", return_value={"entries": entries}):
                    self.assertEqual(launchpad_publish.launchpad_binary_published(source, settings), expected)


    def test_launchpad_waits_through_build_and_binary_import(self):
        now = [0]
        source = {"self_link": "https://example.invalid/source", "status": "Published", "source_package_version": "1.0.4"}
        settings = {"suite": "noble", "architecture": "amd64"}
        binary = {
            "binary_package_name": release_context.PACKAGE,
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
            patch.object(launchpad_publish, "launchpad_sources", return_value=[source]),
            patch.object(launchpad_publish, "launchpad_json", side_effect=response),
            patch.object(launchpad_publish.time, "sleep", side_effect=sleep),
        ):
            launchpad_publish.wait_launchpad(settings, "1.0.4")
        self.assertEqual(now[0], 90)


    def test_launchpad_queue_has_no_publication_deadline(self):
        now = [0]
        source = {"self_link": "https://example.invalid/source", "status": "Published", "source_package_version": "1.0.4"}
        settings = {"suite": "noble", "architecture": "amd64"}
        binary = {
            "binary_package_name": release_context.PACKAGE,
            "binary_package_version": "1.0.4",
            "distro_arch_series_link": "https://api.launchpad.net/1.0/ubuntu/noble/amd64",
            "status": "Published",
        }

        def sleep(seconds):
            self.assertEqual(seconds, 30)
            now[0] += 24 * 60 * 60

        def response(url):
            if url.endswith("getBuilds"):
                return {"entries": [{"buildstate": "Needs building" if now[0] == 0 else "Successfully built"}]}
            return {"entries": [binary]}

        with (
            patch.object(launchpad_publish, "launchpad_sources", return_value=[source]),
            patch.object(launchpad_publish, "launchpad_json", side_effect=response),
            patch.object(launchpad_publish.time, "sleep", side_effect=sleep),
        ):
            launchpad_publish.wait_launchpad(settings, "1.0.4")
        self.assertEqual(now[0], 24 * 60 * 60)

    def test_publication_wait_survives_temporary_api_outages(self):
        for error in (TimeoutError("read timed out"), urllib.error.URLError("connection reset"),
                      urllib.error.HTTPError("https://example.invalid/source", 503, "Unavailable", {}, None)):
            with (
                self.subTest(error=error),
                patch.object(launchpad_publish, "launchpad_progress", side_effect=[error, (4, True)]),
                patch.object(launchpad_publish.time, "sleep") as sleep,
            ):
                launchpad_publish.wait_launchpad({"suite": "noble"}, "1.0.4")
            sleep.assert_called_once_with(30)

    def test_publication_wait_reports_permanent_api_errors(self):
        error = urllib.error.HTTPError("https://example.invalid/source", 403, "Forbidden", {}, None)
        self.addCleanup(error.close)
        with (
            patch.object(launchpad_publish, "launchpad_progress", side_effect=error),
            patch.object(launchpad_publish.time, "sleep") as sleep,
        ):
            with self.assertRaises(urllib.error.HTTPError):
                launchpad_publish.wait_launchpad({"suite": "noble"}, "1.0.4")
        sleep.assert_not_called()


    def test_launchpad_build_failure_is_reported_immediately(self):
        with (
            patch.object(launchpad_publish, "launchpad_sources", return_value=[{"self_link": "https://example.invalid/source"}]),
            patch.object(launchpad_publish, "launchpad_json", return_value={"entries": [{"buildstate": "Failed to build"}]}),
            patch.object(launchpad_publish.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(ValueError, "Failed to build"):
                launchpad_publish.wait_launchpad({}, "1.0.4")
        sleep.assert_not_called()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check immutable GitHub assets without redundant downloads."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release_publish
from apt_repo import sha256


class GithubPublishTests(unittest.TestCase):
    def test_draft_asset_digests_are_read_from_rest_metadata(self):
        url = "https://api.github.com/repos/example/folders/releases/123"
        metadata = {"draft": True, "assets": [{"name": "package.deb", "digest": "sha256:abc"}]}
        with patch.object(release_publish, "github_json", side_effect=[{"apiUrl": url}, metadata]) as query:
            self.assertEqual(release_publish.find_github_release("example/folders", "v1.2.4"), metadata)
        self.assertEqual(query.call_args_list[1].args, ("api", url))

    def test_matching_asset_is_verified_without_a_second_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package.deb"
            package.write_bytes(b"checked binary")
            existing = {"assets": [{"name": package.name, "digest": "sha256:" + sha256(package)}]}
            with patch.object(release_publish, "find_github_release", return_value=existing), \
                    patch.object(release_publish, "run") as run:
                release_publish.publish_github(root, {"upstream": "1.2.4"}, {"github_repository": "example/folders"})
            run.assert_not_called()
            existing["assets"][0]["digest"] = "sha256:changed"
            with patch.object(release_publish, "find_github_release", return_value=existing):
                with self.assertRaisesRegex(ValueError, "asset differs"):
                    release_publish.publish_github(root, {"upstream": "1.2.4"}, {"github_repository": "example/folders"})

    def test_temporary_connection_errors_do_not_mean_a_missing_release(self):
        unavailable = subprocess.CompletedProcess([], 1, "", "error connecting to api.github.com")
        ready = subprocess.CompletedProcess([], 0, json.dumps({"apiUrl": "release-url"}), "")
        with patch.object(release_publish.subprocess, "run", side_effect=[unavailable] * 5 + [ready]) as request, \
                patch.object(release_publish.time, "sleep") as sleep:
            self.assertEqual(release_publish.github_json("release", "view", "v1.2.4", allow_missing=True),
                             {"apiUrl": "release-url"})
        self.assertEqual(request.call_count, 6)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10, 20, 40, 80])

    def test_only_an_explicit_missing_release_allows_creation(self):
        missing = subprocess.CompletedProcess([], 1, "", "release not found\n")
        denied = subprocess.CompletedProcess([], 1, "", "gh: Forbidden (HTTP 403)")
        with patch.object(release_publish.subprocess, "run", return_value=missing):
            self.assertIsNone(release_publish.github_json("release", "view", "v1.2.4", allow_missing=True))
        with patch.object(release_publish.subprocess, "run", return_value=denied), \
                patch.object(release_publish.time, "sleep") as sleep:
            with self.assertRaises(subprocess.CalledProcessError):
                release_publish.github_json("release", "view", "v1.2.4", allow_missing=True)
        sleep.assert_not_called()

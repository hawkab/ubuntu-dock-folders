# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Keep published channels available while Launchpad needs attention."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release


class ReleasePipelineTests(unittest.TestCase):
    def test_launchpad_failure_does_not_hold_other_channels_in_draft(self):
        events = []
        manifest = {"upstream": "9.8.7"}
        settings = {"github_repository": "example/folders", "apt_url": "https://example.invalid/apt/"}

        def launchpad(*args):
            events.append("launchpad")
            raise ValueError("Launchpad requires attention")

        def publish(*args):
            self.assertEqual(args, ("gh", "release", "edit", "v9.8.7", "--repo", "example/folders", "--draft=false"))
            events.append("public")

        with (
            patch.object(release, "publish_github", side_effect=lambda *args: events.append("github")),
            patch.object(release, "publish_apt", side_effect=lambda *args: events.append("apt")),
            patch.object(release, "run", side_effect=publish),
            patch.object(release, "upload_launchpad", side_effect=launchpad),
            patch.object(release, "wait_launchpad") as wait,
        ):
            with self.assertRaisesRegex(ValueError, "requires attention"):
                release.publish_release(Path("/prepared"), manifest, settings, {})
        self.assertEqual(events, ["github", "apt", "public", "launchpad"])
        wait.assert_not_called()

    def test_release_waits_for_every_launchpad_target(self):
        targets = [{"suite": "noble", "version": "9.8.7-1ubuntu24.04.1"},
                   {"suite": "resolute", "version": "9.8.7-1ubuntu26.04.1"}]
        settings = {"github_repository": "example/folders", "apt_url": "https://example.invalid/apt/"}
        with (
            patch.object(release, "publish_github"), patch.object(release, "publish_apt"),
            patch.object(release, "run"), patch.object(release, "upload_launchpad"),
            patch.object(release, "source_uploads", return_value=targets),
            patch.object(release, "wait_launchpad") as wait,
        ):
            release.publish_release(Path("/prepared"), {"upstream": "9.8.7"}, settings, {})
        self.assertEqual([call.args for call in wait.call_args_list],
                         [(settings | {"suite": target["suite"]}, target["version"]) for target in targets])

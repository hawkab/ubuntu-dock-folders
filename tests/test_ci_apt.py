# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check APT recovery before checkout and stop permanent repository errors."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class AptRecoveryTests(unittest.TestCase):
    def wrapper(self, workflow):
        data = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text())
        job = data["jobs"]["check" if workflow == "check.yml" else "publish"]
        step = next(item for item in job["steps"] if "cat > \"$APT_CONFIG.retry\"" in item.get("run", ""))
        return step["run"].split("<<'APT_RETRY'\n", 1)[1].split("\nAPT_RETRY", 1)[0]

    def run_apt(self, failures):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "apt.json").write_text(json.dumps(failures))
            (root / "apt-get").write_text(
                "#!/usr/bin/python3\nimport json, os, pathlib, sys\n"
                "p = pathlib.Path(os.environ['APT_STATE'])\n"
                "items = json.loads(p.read_text())\n"
                "assert os.environ['LC_ALL'] == 'C'\n"
                "assert sys.argv[1:] == ['update']\n"
                "if not items: sys.exit(0)\n"
                "print(items.pop(0))\np.write_text(json.dumps(items))\nsys.exit(100)\n")
            (root / "sleep").write_text("#!/bin/sh\nprintf '%s\\n' \"$1\" >> \"$APT_SLEEPS\"\n")
            script = root / "retry"
            script.write_text(self.wrapper("check.yml"))
            for executable in [script, root / "apt-get", root / "sleep"]:
                executable.chmod(0o755)
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", APT_STATE=str(root / "apt.json"),
                       APT_SLEEPS=str(root / "sleeps"))
            result = subprocess.run([str(script), "update"], env=env, text=True, capture_output=True)
            sleeps = (root / "sleeps").read_text().splitlines() if (root / "sleeps").exists() else []
            return result, sleeps

    def test_both_workflows_use_the_same_recovery(self):
        self.assertEqual(self.wrapper("check.yml"), self.wrapper("release.yml"))

    def test_connection_failure_recovers_without_an_attempt_budget(self):
        error = "E: Failed to fetch http://example.test/InRelease  Could not connect to example.test:80, connection timed out\nE: Some index files failed to download."
        result, sleeps = self.run_apt([error] * 9)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sleeps, ["5", "10", "20", "40", "80", "160", "300", "300", "300"])

    def test_signature_errors_are_not_retried(self):
        result, sleeps = self.run_apt(["E: The repository 'https://example.test' is not signed."])
        self.assertEqual(result.returncode, 100)
        self.assertEqual(sleeps, [])

    def test_missing_package_does_not_loop_after_a_connection_error(self):
        error = "E: Failed to fetch http://example.test/pkg.deb  Connection failed\nE: Unable to locate package missing"
        result, sleeps = self.run_apt([error])
        self.assertEqual(result.returncode, 100)
        self.assertEqual(sleeps, [])

    def test_http_not_found_is_not_retried(self):
        result, sleeps = self.run_apt(["E: Failed to fetch http://example.test/pkg.deb  404 Not Found"])
        self.assertEqual(result.returncode, 100)
        self.assertEqual(sleeps, [])

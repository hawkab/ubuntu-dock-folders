# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check profile identities across runtimes and cached frontend catalogs."""

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from adapters.application_identity import pwa_entries
from adapters import application_identity
from adapters.runtime import CoreRuntime
from backend_build import frontend

ROOT = Path(__file__).resolve().parents[1]
APP = "a" * 32
DESKTOP = f"chrome-{APP}-Default.desktop"


def info(profile):
    return SimpleNamespace(get_id=lambda: DESKTOP, get_name=lambda: "Work app",
        get_executable=lambda: "chrome", get_startup_wm_class=lambda: "crx_" + APP,
        get_commandline=lambda: f'chrome "--profile-directory={profile}" --app-id={APP}')


class PwaTests(unittest.TestCase):
    def setUp(self):
        modules = patch.dict(sys.modules, {"application_identity":application_identity})
        modules.start()
        self.addCleanup(modules.stop)
        self.core = CoreRuntime(ROOT)
        self.addCleanup(self.core.close)

    def test_gjs_and_qt_use_the_same_profile_index(self):
        entries = pwa_entries([info("Profile 3")])
        expected = self.core.call("pwaIndex", entries)
        self.assertEqual(expected[f"chrome-{APP}-Profile_3"], DESKTOP)
        runner = frontend(self, "plasma") / "code/dock-folders-core-runner"
        result = subprocess.run([str(runner), str(ROOT / "core/windowIdentity.js"), "pwaIndex"],
            input=json.dumps(entries), text=True, capture_output=True, check=True, timeout=3)
        self.assertEqual(json.loads(result.stdout), expected)
        query = {"index":expected, "classes":[f"chrome-{APP}-Profile_3"], "fallback":"google-chrome.desktop"}
        self.assertEqual(self.core.call("matchPwa", query), DESKTOP)

    def test_malformed_exec_is_never_executed(self):
        entry = info("Default")
        entry.get_commandline = lambda: 'chrome "--profile-directory=unfinished'
        self.assertEqual(self.core.call("pwaIndex", pwa_entries([entry])), {})

    def test_xfce_reindexes_changed_launchers_without_window_time_ipc(self):
        spec = importlib.util.spec_from_file_location("pwa_window_catalog", ROOT / "xfce/window_catalog.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        catalog = module.WindowCatalog.__new__(module.WindowCatalog)
        catalog.core = self.core
        catalog.groups = {}
        catalog.queue = lambda: None
        window = lambda profile: SimpleNamespace(get_class_instance_name=lambda: f"chrome-{APP}-{profile}",
                                                get_class_group_name=lambda: "google-chrome", get_name=lambda: "Work")
        with patch.object(module.Gio.AppInfo, "get_all", return_value=[info("Profile 3")]):
            catalog.refresh_catalog()
        with patch.object(self.core, "call", side_effect=AssertionError("Window lookup called the worker")):
            self.assertEqual(catalog.desktop(window("Profile_3")), DESKTOP)
            self.assertNotEqual(catalog.desktop(window("Profile_4")), DESKTOP)
        with patch.object(module.Gio.AppInfo, "get_all", return_value=[info("Profile 4")]):
            catalog.refresh_catalog()
        self.assertEqual(catalog.desktop(window("Profile_4")), DESKTOP)
        self.assertNotEqual(catalog.desktop(window("Profile_3")), DESKTOP)
        with patch.object(module.Gio.AppInfo, "get_all", return_value=[]):
            catalog.refresh_catalog()
        self.assertNotEqual(catalog.desktop(window("Profile_4")), DESKTOP)

    def test_xfce_keeps_ambiguous_profiles_out_of_grouped_classes(self):
        spec = importlib.util.spec_from_file_location("pwa_window_catalog", ROOT / "xfce/window_catalog.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        catalog = module.WindowCatalog.__new__(module.WindowCatalog)
        catalog.pwas = {f"crx_{APP}":"", f"chrome-{APP}-Profile_3":DESKTOP}
        self.assertEqual(catalog.pwa_desktop([f"crx_{APP}"]), f"wm:crx_{APP}")
        self.assertEqual(catalog.pwa_desktop([f"crx_{APP}", f"chrome-{APP}-Profile_3"]), DESKTOP)

    def test_xfce_does_not_use_the_browser_executable_as_a_pwa_alias(self):
        spec = importlib.util.spec_from_file_location("pwa_window_catalog", ROOT / "xfce/window_catalog.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        pwa = info("Profile 3")
        pwa.get_executable = lambda: "/opt/google/chrome/google-chrome"
        browser = SimpleNamespace(get_id=lambda:"google-chrome.desktop", get_name=lambda:"Google Chrome",
            get_executable=pwa.get_executable, get_startup_wm_class=lambda:None)
        catalog = module.WindowCatalog.__new__(module.WindowCatalog)
        catalog.core, catalog.groups = self.core, {}
        with patch.object(module.Gio.AppInfo, "get_all", return_value=[pwa,browser]):
            catalog.refresh_catalog()
        window = SimpleNamespace(get_class_instance_name=lambda:"google-chrome",
            get_class_group_name=lambda:"Google-chrome", get_name=lambda:"Browser")
        self.assertEqual(catalog.desktop(window), "google-chrome.desktop")


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check forced Xfce popup teardown without running a desktop session."""

import os
from pathlib import Path
import subprocess
import unittest
from backend_build import frontend

ROOT = Path(__file__).resolve().parent.parent


class XfcePopupTests(unittest.TestCase):
    def test_force_close_cancels_a_closing_animation(self):
        frontend(self, "xfce")
        code = '''
import sys
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,sys.argv[1])
from folder_popup import FolderPopup
popup=FolderPopup.__new__(FolderPopup)
popup.closing=True
popup.frame=123
popup.grabbed=False
popup.window=Mock()
popup.controller=SimpleNamespace(popup=popup,folder_tooltips=Mock())
popup.close(True)
assert popup.frame==123
popup.window.destroy.assert_not_called()
popup.close(False)
assert popup.frame==0
popup.window.remove_tick_callback.assert_called_once_with(123)
popup.window.destroy.assert_called_once()
assert popup.controller.popup is None
popup.controller.folder_tooltips.assert_called_once_with(True)
print('FORCE_POPUP_CLOSE_PASSED')
'''
        result = subprocess.run(["/usr/bin/python3", "-c", code, str(ROOT / "xfce")],
            env=dict(os.environ, DOCK_FOLDERS_EXTENSION=str(ROOT / "build/extension")),
            text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FORCE_POPUP_CLOSE_PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check partial JSON and UTF-8 writes in live compositor logs."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from probe_log import records


class ProbeLogTests(unittest.TestCase):
    def test_nested_partial_record_is_read_only_after_its_newline(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "log"
            file.write_bytes(b'warning\nqml: PROBE {"value":1}\nqml: PROBE {"nested":{"x":2}')
            self.assertEqual(records(file, "PROBE"), [{"value": 1}])
            with file.open("ab") as output:
                output.write(b'}\n')
            self.assertEqual(records(file, "PROBE"), [{"value": 1}, {"nested": {"x": 2}}])

    def test_incomplete_utf8_tail_does_not_break_complete_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "log"
            file.write_bytes(b'qml: PROBE {"value":1}\nqml: PROBE {"name":"\xd0')
            self.assertEqual(records(file, "PROBE"), [{"value": 1}])

    def test_invalid_completed_record_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "log"
            file.write_bytes(b'qml: PROBE {"invalid":}\n')
            with self.assertRaises(json.JSONDecodeError):
                records(file, "PROBE")


if __name__ == "__main__":
    unittest.main()

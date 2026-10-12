# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise core transport failures with disposable local worker processes."""

import subprocess
import threading
import time
import unittest
from unittest.mock import patch

from adapters.runtime import CoreRuntime


class RuntimeTests(unittest.TestCase):
    def worker(self, code):
        original = subprocess.Popen
        with patch("adapters.runtime.subprocess.Popen",
                   lambda *_args, **kwargs: original(["/usr/bin/python3", "-u", "-c", code], **kwargs)):
            return CoreRuntime()

    def bounded_failure(self, code, value=None):
        runtime = self.worker(code)
        watchdog = threading.Timer(3, runtime.process.kill)
        watchdog.start()
        started = time.monotonic()
        try:
            with self.assertRaises(TimeoutError):
                runtime.call("contract", value)
            self.assertLess(time.monotonic() - started, 2.9)
            self.assertIsNotNone(runtime.process.poll())
            runtime.close()
        finally:
            watchdog.cancel()
            runtime.close()

    def test_partial_response_obeys_deadline(self):
        self.bounded_failure("import sys,time; sys.stdin.readline(); "
                             "sys.stdout.write('{\"ok\":'); sys.stdout.flush(); time.sleep(30)")

    def test_unread_large_request_obeys_deadline(self):
        self.bounded_failure("import time; time.sleep(30)", "x" * (1024 * 1024))

    def test_stderr_backpressure_does_not_block_a_response(self):
        runtime = self.worker("import sys; sys.stderr.write('warning\\n' * 30000); "
                              "sys.stderr.flush(); sys.stdin.readline(); "
                              "print('{\"ok\":true,\"result\":123}',flush=True)")
        try:
            self.assertEqual(runtime.call("contract"), 123)
        finally:
            runtime.close()

    def test_malformed_responses_terminate_the_worker(self):
        for reply in ("not json", "{}", "[]", '{"ok":true}'):
            with self.subTest(reply=reply):
                runtime = self.worker("import sys,time; sys.stdin.readline(); "
                                      f"print({reply!r},flush=True); time.sleep(30)")
                try:
                    with self.assertRaises(ValueError):
                        runtime.call("contract")
                    self.assertIsNotNone(runtime.process.poll())
                    with self.assertRaisesRegex(RuntimeError, "closed"):
                        runtime.call("contract")
                finally:
                    runtime.close()

    def test_reply_size_is_bounded_without_a_newline(self):
        runtime = self.worker("import sys,time; sys.stdin.readline(); "
                              "sys.stdout.write('x'*8192); sys.stdout.flush(); time.sleep(30)")
        runtime.MAX_REPLY = 4096
        try:
            with self.assertRaisesRegex(ValueError, "exceeded"):
                runtime.call("contract")
            self.assertIsNotNone(runtime.process.poll())
        finally:
            runtime.close()

    def test_normal_unicode_and_large_responses(self):
        runtime = CoreRuntime()
        try:
            result = runtime.call("folderCatalog", {"sources": [{"id": "source", "name": "Программы",
                "categories": ["Utility"]}], "entries": {f"app-{index}.desktop": {
                    "label": "应用 " + str(index), "categories": ["Utility"]} for index in range(2000)}})
            self.assertEqual(result[0]["name"], "Программы")
            self.assertEqual(len(result[0]["apps"]), 2000)
            self.assertIn("reconcile", runtime.call("contract")["commands"])
        finally:
            runtime.close()

    def test_batch_motion_and_registered_frames_match_direct_requests(self):
        runtime = CoreRuntime()
        try:
            values = {"orbitSpeed":90,"hoverOrbitSpeed":30}
            requests = [{"args":[48,6,2.3,60,False,"test",0,True,.5,True],
                         "angle":angle,"velocity":90,"elapsed":33,"allowed":True} for angle in (0,90,180)]
            expected = [runtime.call("orbitMiniatures",dict(request,values=values)) for request in requests]
            self.assertEqual(runtime.call("orbitMiniaturesBatch",{"values":values,"items":requests}),expected)
            source = {"id":"test","mode":"flow","speed":180,"rect":{"x":0,"y":0,"width":200,"height":100},
                      "anchor":{"x":100,"y":200},"edge":0,"points":[{"x":0,"y":0},{"x":200,"y":100}]}
            self.assertTrue(runtime.call("registerFrame",source))
            for time in (0,.3,.7,1):
                direct = runtime.call("frame",dict(source,time=time,opening=True,id=None))
                self.assertEqual(runtime.call("frame",{"id":"test","time":time,"opening":True}),direct)
            self.assertTrue(runtime.call("releaseFrame","test"))
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main()

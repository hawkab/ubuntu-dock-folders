# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check image cache budgets and theme invalidation on a private GTK display."""

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IconCacheTests(unittest.TestCase):
    def test_size_sweep_is_bounded_and_theme_changes_clear_cached_pixels(self):
        code = '''
import sys
sys.path.insert(0,sys.argv[1])
from icons import IconCache
cache=IconCache();cache.limit=8;cache.budget=65536
for size in range(16,100):
 cache.get('test.missing.desktop',size)
 assert len(cache.icons)<=cache.limit
 assert cache.bytes<=cache.budget
cache.theme.emit('changed')
assert not cache.icons and not cache.sources and cache.bytes==0
cache.get('test.missing.desktop',32)
assert cache.icons
cache.close()
assert not cache.icons and cache.bytes==0
'''
        result = subprocess.run(['/usr/bin/python3','-c',code,str(ROOT/'xfce')],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

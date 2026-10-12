#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Provide Cairo paths and color conversion for Xfce surfaces."""

import math
from gi.repository import Gdk

def rounded(context, x, y, width, height, radius):
    for cx, cy, start in ((x + width - radius, y + radius, -math.pi / 2),
                          (x + width - radius, y + height - radius, 0),
                          (x + radius, y + height - radius, math.pi / 2),
                          (x + radius, y + radius, math.pi)):
        context.arc(cx, cy, radius, start, start + math.pi / 2)
    context.close_path()


def color(value, alpha=1):
    result = Gdk.RGBA()
    result.parse(value or "#26262a")
    return result.red, result.green, result.blue, alpha

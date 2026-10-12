# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Locate built frontends and report optional backend checks explicitly."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTENDS = {"gnome": "extension", "plasma": "plasma/contents", "xfce": "xfce/shared"}


def frontend(test, desktop):
    marker = ROOT / "build" / ("extension" if desktop == "gnome" else desktop)
    command = "make build" if desktop == "gnome" else "make build-" + desktop
    if desktop != "gnome" and not marker.exists():
        test.skipTest(f"{desktop.title()} backend is not built ({marker}); run {command}")
    test.assertTrue(marker.is_dir(), f"The GNOME build is required; run {command}")
    return ROOT / "build" / FRONTENDS[desktop]

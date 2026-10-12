# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Release window resources once, including programmatic or parent destruction."""


def on_window_close(window, callback):
    closed = False

    def close(*_args):
        nonlocal closed
        if not closed:
            closed = True
            callback(window)
        return False

    window.connect("close-request", close)
    window.connect("unrealize", close)

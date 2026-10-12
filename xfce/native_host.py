# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Expose the shared GTK controller as native widgets in a Wayland panel."""

from diagnostics import install_logging
install_logging()
from panel import Controller


class NativeHost(Controller):
    def __init__(self, plugin, size, orientation):
        super().__init__(size=size, orientation=orientation, host=plugin)
        self.plugin = plugin

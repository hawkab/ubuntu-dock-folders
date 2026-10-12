# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Drive a virtual pointer in a private headless compositor."""

import os
import subprocess
from pathlib import Path


class Pointer:
    def __init__(self, width, height):
        root = Path(__file__).resolve().parent / "native"
        build = Path(os.environ["HOME"]) / "pointer"
        build.mkdir(exist_ok=True)
        protocol = root / "virtual-pointer.xml"
        subprocess.run(["wayland-scanner", "client-header", str(protocol), str(build / "virtual-pointer.h")], check=True)
        subprocess.run(["wayland-scanner", "private-code", str(protocol), str(build / "virtual-pointer.c")], check=True)
        keyboard = root / "virtual-keyboard.xml"
        subprocess.run(["wayland-scanner", "client-header", str(keyboard), str(build / "virtual-keyboard.h")], check=True)
        subprocess.run(["wayland-scanner", "private-code", str(keyboard), str(build / "virtual-keyboard.c")], check=True)
        flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "wayland-client", "xkbcommon"], text=True).split()
        subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-I" + str(build), str(root / "wayland-pointer.c"),
                        str(build / "virtual-pointer.c"), str(build / "virtual-keyboard.c"),
                        "-o", str(build / "pointer"), *flags], check=True)
        self.process = subprocess.Popen([str(build / "pointer")], stdin=subprocess.PIPE, text=True)
        self.width, self.height = width, height

    def move(self, x, y):
        self.process.stdin.write(f"m {int(x)} {int(y)} {self.width} {self.height}\n")
        self.process.stdin.flush()

    def button(self, down):
        self.process.stdin.write(f"b {int(down)}\n")
        self.process.stdin.flush()

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=3)

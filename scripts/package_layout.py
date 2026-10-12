# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Finalize Debian file layout, permissions, documentation and checksums."""

import gzip
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def finalize(stage, package, root=ROOT, strip_native=True):
    """Normalize a staged package without modifying any build outputs."""
    multiarch = subprocess.check_output(["dpkg-architecture", "-qDEB_HOST_MULTIARCH"], text=True).strip()
    for file in list((stage / "usr").rglob("*")):
        if not file.is_file() or file.is_symlink():
            continue
        with file.open("rb") as stream:
            native = stream.read(4) == b"\x7fELF"
        if not native:
            continue
        if strip_native:
            subprocess.run(["strip", "--strip-unneeded", str(file)], check=True)
        if file.is_relative_to(stage / "usr/share"):
            target = stage / "usr/lib" / multiarch / "ubuntu-dock-folders" / file.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ValueError(f"Duplicate native package filename: {file.name}")
            shutil.move(file, target)
            file.symlink_to(os.path.relpath(target, file.parent))
            target.chmod(0o644 if target.suffix == ".so" else 0o755)
    documentation = stage / "usr/share/doc" / package
    documentation.mkdir(parents=True, exist_ok=True)
    (documentation / "changelog.Debian.gz").write_bytes(gzip.compress(
        (root / "debian/changelog").read_bytes(), mtime=0))
    for executable in (stage / "usr/bin").glob("*"):
        source = root / "packaging" / (executable.name + ".1")
        if source.is_file():
            manual = stage / "usr/share/man/man1" / (source.name + ".gz")
            manual.parent.mkdir(parents=True, exist_ok=True)
            manual.write_bytes(gzip.compress(source.read_bytes(), mtime=0))
    stage.chmod(0o755)
    for file in stage.rglob("*"):
        if not file.is_symlink():
            file.chmod(0o755 if file.is_dir() or file.stat().st_mode & 0o111 else 0o644)
    control = stage / "DEBIAN"
    conffiles = control / "conffiles"
    excluded = {line.lstrip("/") for line in conffiles.read_text().splitlines()} if conffiles.exists() else set()
    sums = []
    size = 0
    for file in sorted(stage.rglob("*")):
        relative = file.relative_to(stage).as_posix()
        if relative.startswith("DEBIAN/") or not file.is_file() or file.is_symlink():
            continue
        size += file.stat().st_size
        if relative not in excluded:
            with file.open("rb") as stream:
                digest = hashlib.file_digest(stream, "md5").hexdigest()
            sums.append(f"{digest}  {relative}\n")
    (control / "md5sums").write_text("".join(sums))
    (control / "md5sums").chmod(0o644)
    metadata = control / "control"
    if metadata.exists():
        lines = [line for line in metadata.read_text().splitlines() if not line.startswith("Installed-Size:")]
        metadata.write_text("\n".join(lines) + f"\nInstalled-Size: {(size + 1023) // 1024}\n")

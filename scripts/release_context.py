# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Load release configuration and construct a reproducible source snapshot."""

import os
import platform
import re
import shutil
import tomllib
from pathlib import Path

from apt_repo import ROOT, run
from publication_files import source_file

PACKAGE = "ubuntu-dock-folders"
STATE = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / PACKAGE / "publishing"
)


def config():
    return tomllib.loads((ROOT / "packaging/release.toml").read_text())


def signing_environment():
    env = os.environ.copy()
    if "GNUPGHOME" not in env and (STATE / "gnupg").is_dir():
        env["GNUPGHOME"] = str(STATE / "gnupg")
    return env


def changelog(field, root=None):
    return run("dpkg-parsechangelog", "-S", field, cwd=root or ROOT, capture=True).strip()


def validate_build_series(settings):
    """Require native binaries to be built on the Ubuntu series they are published for."""
    distribution = platform.freedesktop_os_release()
    series = distribution.get("VERSION_CODENAME", distribution.get("UBUNTU_CODENAME"))
    if distribution.get("ID") != "ubuntu" or series != settings["suite"]:
        raise ValueError(f"Build the {settings['suite']} binary in an Ubuntu {settings['suite']} "
                         "build environment; native library dependencies are series-specific.")


def source_files():
    files = run(
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        cwd=ROOT,
        capture=True,
    ).split("\0")
    return sorted(set(name for name in files if name and source_file(name) and (
        (ROOT / name).exists() or (ROOT / name).is_symlink())))


def snapshot(destination):
    """Copy source files and relative links whose targets stay inside the checkout."""
    for name in source_files():
        source = ROOT / name
        if not source.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(f"Source path leaves the checkout: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            link = os.readlink(source)
            if Path(link).is_absolute() or not source.exists():
                raise ValueError(f"Source symlink must have an existing relative target: {name}")
            target.symlink_to(link)
        else:
            shutil.copy2(source, target)


def launchpad_targets(settings, version):
    targets = settings.get("launchpad_targets")
    if targets is None:
        return [{"suite": settings["suite"], "version": version}]
    upstream = version.split("-")[0]
    result = []
    for target in targets:
        suite = target["suite"]
        suffix = target["version_suffix"]
        if not re.fullmatch(r"[a-z][a-z0-9-]*", suite) or not re.fullmatch(r"[0-9A-Za-z.-]+", suffix):
            raise ValueError("Invalid Launchpad target")
        result.append({"suite": suite, "version": upstream + "-" + suffix})
    if len({target["suite"] for target in result}) != len(result):
        raise ValueError("Duplicate Launchpad series")
    if len({target["version"] for target in result}) != len(result):
        raise ValueError("Launchpad series need distinct source versions")
    if {"suite": settings["suite"], "version": version} not in result:
        raise ValueError("Launchpad targets must include the release binary's suite and version")
    return result

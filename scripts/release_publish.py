# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Publish immutable assets to GitHub Releases and the signed APT archive."""

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from apt_repo import run, sha256, update_archive

import release_context as context

def apt_git_environment():
    env = os.environ.copy()
    identity = Path(os.environ.get("APT_DEPLOY_KEY", context.STATE / "apt-deploy"))
    if identity.is_file():
        hosts = context.ROOT / "packaging/github-known-hosts"
        env["GIT_SSH_COMMAND"] = " ".join(
            shlex.quote(part)
            for part in (
                "ssh",
                "-i",
                str(identity),
                "-oIdentitiesOnly=yes",
                "-oBatchMode=yes",
                "-oStrictHostKeyChecking=yes",
                f"-oUserKnownHostsFile={hosts}",
            )
        )
    return env


def publish_apt(directory, settings, env):
    with tempfile.TemporaryDirectory(prefix="dock-folders-apt-publish-") as temporary:
        checkout = Path(temporary) / "apt"
        git_env = apt_git_environment()
        run(
            "git",
            "clone",
            "--branch",
            settings["apt_branch"],
            f"git@github.com:{settings['apt_repository']}.git",
            checkout,
            env=git_env,
        )
        manifest = json.loads((directory / "release.json").read_text())
        for binary in manifest["binaries"]:
            update_archive(directory / binary["file"], checkout, settings | {"suite": binary["suite"]},
                           env=env, source_root=context.ROOT)
        run("git", "add", "--all", cwd=checkout)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=checkout).returncode == 0:
            return
        run(
            "git",
            "-c",
            "user.name=Grigory Olshansky",
            "-c",
            "user.email=14372308+hawkab@users.noreply.github.com",
            "-c",
            "commit.gpgsign=true",
            "-c",
            f"user.signingkey={settings['signing_fingerprint']}",
            "commit",
            "-m",
            f"Publish Ubuntu Dock Folders {context.changelog('Version')}",
            cwd=checkout,
            env=env,
        )
        run("git", "push", "origin", settings["apt_branch"], cwd=checkout, env=git_env)


def publish_github(directory, manifest, settings):
    repository = settings["github_repository"]
    tag = "v" + manifest["upstream"]
    lookup = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repository, "--json", "isDraft,assets"],
        capture_output=True,
        text=True,
    )
    if lookup.returncode:
        notes = (
            f"Ubuntu Dock Folders {manifest['upstream']}\n\n"
            "Ubuntu 24.04: GNOME 46. Ubuntu 26.04: GNOME 50, KDE Plasma 6.6 and Xfce 4.20.\n\n"
            f"Install and receive updates: {settings['apt_url']}\n\n"
            f"PPA: https://launchpad.net/~{settings['launchpad_owner']}"
            f"/+archive/ubuntu/{settings['launchpad_archive']}\n\n"
            + context.changelog("Changes")
            + "\n\nChecksums and source packages are included below.\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md") as body:
            body.write(notes)
            body.flush()
            run(
                "gh",
                "release",
                "create",
                tag,
                "--repo",
                repository,
                "--verify-tag",
                "--title",
                f"Ubuntu Dock Folders {manifest['upstream']}",
                "--notes-file",
                body.name,
                "--draft",
            )
        assets = {}
    else:
        assets = {asset["name"]: asset for asset in json.loads(lookup.stdout)["assets"]}
    for file in sorted(directory.iterdir()):
        if file.name in assets:
            digest = assets[file.name].get("digest")
            if digest:
                if digest != "sha256:" + sha256(file):
                    raise ValueError(f"GitHub asset differs: {file.name}")
            else:
                with tempfile.TemporaryDirectory() as download:
                    run(
                        "gh",
                        "release",
                        "download",
                        tag,
                        "--repo",
                        repository,
                        "--pattern",
                        file.name,
                        "--dir",
                        download,
                    )
                    if sha256(Path(download) / file.name) != sha256(file):
                        raise ValueError(f"GitHub asset differs: {file.name}")
        else:
            run("gh", "release", "upload", tag, file, "--repo", repository)

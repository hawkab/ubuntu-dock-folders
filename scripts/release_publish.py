# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Publish immutable assets to GitHub Releases and the signed APT archive."""

import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

from apt_repo import run, sha256, update_archive

import release_context as context


def github_json(*arguments, allow_missing=False):
    """Read GitHub metadata, retrying temporary transport failures."""
    command = ["gh", *arguments]
    delay = 5
    while True:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        error = result.stderr or ""
        if allow_missing and error.strip().lower() == "release not found":
            return None
        if not re.search(r"error connecting|timed out|connection reset|temporary failure|"
                         r"TLS handshake|HTTP (429|500|502|503|504)|API rate limit exceeded", error, re.I):
            raise subprocess.CalledProcessError(result.returncode, command, result.stdout, error)
        print(f"GitHub API unavailable; retrying in {delay}s", flush=True)
        time.sleep(delay)
        delay = min(delay * 2, 300)


def find_github_release(repository, tag):
    """Return REST release metadata, including draft asset digests."""
    release = github_json("release", "view", tag, "--repo", repository, "--json", "apiUrl", allow_missing=True)
    return github_json("api", release["apiUrl"]) if release is not None else None


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
    existing = find_github_release(repository, tag)
    if existing is None:
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
        assets = {asset["name"]: asset for asset in existing["assets"]}
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

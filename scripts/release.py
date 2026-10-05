#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Build, test, sign and publish one release to GitHub, APT and Launchpad."""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

from apt_repo import ROOT, run, sha256, update_archive

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


def changelog(field, root=ROOT):
    return run("dpkg-parsechangelog", "-S", field, cwd=root, capture=True).strip()


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
    return sorted(set(name for name in files if name and (ROOT / name).exists()))


def snapshot(destination):
    for name in source_files():
        source = ROOT / name
        if source.is_symlink():
            raise ValueError(f"Source symlinks must be reviewed: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def build_release(settings, env):
    version = changelog("Version")
    if not re.fullmatch(r"[0-9A-Za-z.-]+", version):
        raise ValueError(
            "Use an APT version with GitHub-safe filenames, for example 1.0.2-1ubuntu24.04.1"
        )
    upstream = version.split("-")[0]
    if not re.fullmatch(r"\d+\.\d+\.\d+", upstream):
        raise ValueError("Release version must use major.minor.patch")
    if changelog("Distribution") != settings["suite"]:
        raise ValueError("Changelog suite differs from release configuration")
    if run("dpkg", "--print-architecture", capture=True).strip() != settings["architecture"]:
        raise ValueError("Build architecture differs from release configuration")
    output = ROOT / "dist/releases" / upstream
    if output.exists():
        raise ValueError(f"{output} already exists; use --prepared to resume it or move it aside")
    output.mkdir(parents=True)
    env = env | {"SOURCE_DATE_EPOCH": changelog("Timestamp")}
    with tempfile.TemporaryDirectory(prefix="dock-folders-release-") as temporary:
        temporary = Path(temporary)
        source = temporary / f"{PACKAGE}-{upstream}"
        snapshot(source)
        orig = temporary / f"{PACKAGE}_{upstream}.orig.tar.xz"
        run(
            "tar",
            "--sort=name",
            f"--mtime=@{env['SOURCE_DATE_EPOCH']}",
            "--owner=0",
            "--group=0",
            "--numeric-owner",
            "--exclude=debian",
            "-cJf",
            orig,
            "-C",
            source,
            ".",
        )
        run("dpkg-buildpackage", "-b", "-us", "-uc", cwd=source, env=env)
        for file in source.glob("dist/*.zip"):
            shutil.copy2(file, output / file.name)
        for file in temporary.glob("*.deb"):
            shutil.copy2(file, output / file.name)
        run("dpkg-buildpackage", "-S", "-us", "-uc", cwd=source, env=env)
        changes = next(temporary.glob("*_source.changes"))
        run("debsign", "--no-re-sign", "-k" + settings["signing_fingerprint"], changes, env=env)
        for pattern in ("*.dsc", "*.tar.xz", "*_source.changes", "*_source.buildinfo"):
            for file in temporary.glob(pattern):
                shutil.copy2(file, output / file.name)
        with tempfile.TemporaryDirectory(prefix="dock-folders-unpack-") as unpack:
            run(
                "dpkg-source",
                "--no-check",
                "-x",
                next(output.glob("*.dsc")),
                Path(unpack) / "source",
            )
    shutil.copy2(ROOT / "packaging/archive-key.asc", output / "archive-key.asc")
    manifest = {
        "version": version,
        "upstream": upstream,
        "suite": settings["suite"],
        "architecture": settings["architecture"],
        "commit": run("git", "rev-parse", "HEAD", cwd=ROOT, capture=True).strip(),
        "dirty": bool(run("git", "status", "--porcelain", cwd=ROOT, capture=True).strip()),
        "files": {file.name: sha256(file) for file in sorted(output.iterdir()) if file.is_file()},
    }
    (output / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
    sums = output / "SHA256SUMS"
    sums.write_text("".join(f"{sha256(file)}  {file.name}\n" for file in sorted(output.iterdir())))
    run(
        "gpg",
        "--batch",
        "--yes",
        "--local-user",
        settings["signing_fingerprint"],
        "--armor",
        "--detach-sign",
        sums,
        env=env,
    )
    return output


def verify_release(directory, settings, env):
    sums = directory / "SHA256SUMS"
    result = run(
        "gpg",
        "--batch",
        "--status-fd=1",
        "--verify",
        directory / "SHA256SUMS.asc",
        sums,
        env=env,
        capture=True,
    )
    if f"[GNUPG:] VALIDSIG {settings['signing_fingerprint']} " not in result:
        raise ValueError("Release has an unexpected signing key")
    expected = set()
    for line in sums.read_text().splitlines():
        digest, name = line.split("  ", 1)
        if Path(name).name != name or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("Invalid checksum manifest")
        file = directory / name
        if not file.is_file() or file.is_symlink() or sha256(file) != digest:
            raise ValueError(f"Artifact checksum mismatch: {name}")
        expected.add(name)
    if expected | {"SHA256SUMS", "SHA256SUMS.asc"} != {p.name for p in directory.iterdir()}:
        raise ValueError("Unexpected release artifacts")
    manifest = json.loads((directory / "release.json").read_text())
    for name, digest in manifest["files"].items():
        if name not in expected or sha256(directory / name) != digest:
            raise ValueError(f"Artifact missing from release manifest: {name}")
    if manifest.get("version") != changelog("Version"):
        raise ValueError("Prepared version differs from the changelog")
    if manifest.get("upstream") != manifest["version"].split("-")[0]:
        raise ValueError("Prepared upstream version differs from the package version")
    for field in ("suite", "architecture"):
        if manifest[field] != settings[field]:
            raise ValueError(f"Release {field} differs from current configuration")
    for source in list(directory.glob("*.dsc")) + list(directory.glob("*_source.changes")):
        run("gpg", "--verify", source, env=env)
    run("dput", "-o", next(directory.glob("*_source.changes")), cwd=directory, env=env)
    return manifest


def launchpad_json(url):
    request = urllib.request.Request(
        url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def launchpad_sources(settings, version, status=None):
    base = (
        f"https://api.launchpad.net/1.0/~{settings['launchpad_owner']}"
        f"/+archive/ubuntu/{settings['launchpad_archive']}"
    )
    query = {
        "ws.op": "getPublishedSources",
        "source_name": PACKAGE,
        "exact_match": "true",
        "version": version,
    }
    if status:
        query["status"] = status
    return launchpad_json(base + "?" + urllib.parse.urlencode(query))["entries"]


def upload_launchpad(directory, manifest, settings, env):
    if launchpad_sources(settings, manifest["version"]):
        print("Launchpad already has this source version", flush=True)
        return
    changes = next(directory.glob("*_source.changes"))
    text = run("gpg", "--batch", "--decrypt", changes, env=env, capture=True)
    section = text.split("Checksums-Sha256:\n", 1)[1].split("\n\n", 1)[0]
    files = []
    for line in section.splitlines():
        if not line.startswith(" "):
            break
        digest, size, name = line.split()
        file = directory / name
        if Path(name).name != name or not file.is_file() or sha256(file) != digest:
            raise ValueError("Source upload checksum mismatch")
        files.append(file)
    if not files:
        raise ValueError("Source changes file contains no artifacts")
    transport = os.environ.get("LAUNCHPAD_UPLOAD_TRANSPORT", settings["launchpad_transport"])
    if transport == "ftp":
        run(
            "dput",
            "-P",
            "-U",
            f"ppa:{settings['launchpad_owner']}/{settings['launchpad_archive']}",
            changes,
            cwd=directory,
            env=env,
        )
        print("Source submitted through dput; Launchpad acceptance/build is pending", flush=True)
        return
    if transport != "sftp":
        raise ValueError("Launchpad transport must be ftp or sftp")
    identity = Path(os.environ.get("LAUNCHPAD_SSH_KEY", STATE / "launchpad-upload"))
    if not identity.is_file():
        raise ValueError("LAUNCHPAD_SSH_KEY must point to the registered upload key")
    incoming = f"~{settings['launchpad_owner']}/ubuntu/{settings['launchpad_archive']}"
    batch = (
        "cd "
        + incoming
        + "\n"
        + "".join(f'put "{file}" "{file.name}"\n' for file in [*files, changes])
    )
    subprocess.run(
        [
            "sftp",
            "-i",
            str(identity),
            "-oIdentitiesOnly=yes",
            "-oBatchMode=yes",
            "-oConnectTimeout=15",
            "-oServerAliveInterval=15",
            "-oServerAliveCountMax=3",
            "-oStrictHostKeyChecking=yes",
            f"-oUserKnownHostsFile={ROOT / 'packaging/launchpad-known-hosts'}",
            "-b",
            "-",
            f"{settings['launchpad_owner']}@ppa.launchpad.net",
        ],
        input=batch,
        text=True,
        check=True,
        timeout=180,
    )
    print("Source uploaded; Launchpad still needs to accept and build it", flush=True)


def launchpad_binary_published(source, settings):
    binaries = launchpad_json(source["self_link"] + "?ws.op=getPublishedBinaries")["entries"]
    architecture = f"/{settings['suite']}/{settings['architecture']}"
    return any(
        binary["status"] == "Published"
        and binary["binary_package_name"] == PACKAGE
        and binary["binary_package_version"] == source["source_package_version"]
        and binary["distro_arch_series_link"].endswith(architecture)
        for binary in binaries
    )


def wait_launchpad(settings, version, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sources = launchpad_sources(settings, version)
        for source in sources:
            builds = launchpad_json(source["self_link"] + "?ws.op=getBuilds")["entries"]
            statuses = {build["buildstate"] for build in builds}
            if statuses & {
                "Failed to build",
                "Dependency wait",
                "Chroot problem",
                "Failed to upload",
            }:
                raise ValueError("Launchpad build needs attention: " + ", ".join(sorted(statuses)))
            if (
                source["status"] == "Published"
                and builds
                and statuses == {"Successfully built"}
                and launchpad_binary_published(source, settings)
            ):
                print("Launchpad binary published", flush=True)
                return
        print("Waiting for Launchpad acceptance, build and binary publication", flush=True)
        time.sleep(30)
    raise ValueError("Launchpad publication pending; resume with the same --prepared directory")


def apt_git_environment():
    env = os.environ.copy()
    identity = Path(os.environ.get("APT_DEPLOY_KEY", STATE / "apt-deploy"))
    if identity.is_file():
        hosts = ROOT / "packaging/github-known-hosts"
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
        update_archive(next(directory.glob("*.deb")), checkout, settings, env=env)
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
            f"Publish Ubuntu Dock Folders {changelog('Version')}",
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
            f"Ubuntu Dock Folders {manifest['upstream']} for Ubuntu 24.04 / GNOME 46.\n\n"
            f"Package version: `{manifest['version']}`.\n\n"
            f"Install and receive updates: {settings['apt_url']}\n\n"
            f"PPA: https://launchpad.net/~{settings['launchpad_owner']}"
            f"/+archive/ubuntu/{settings['launchpad_archive']}\n\n"
            + changelog("Changes")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--wait-seconds", type=int, default=1200)
    args = parser.parse_args()
    settings = config()
    env = signing_environment()
    if args.publish and run("git", "status", "--porcelain", cwd=ROOT, capture=True).strip():
        raise ValueError("Commit reviewed changes before publishing")
    directory = args.prepared.resolve() if args.prepared else None
    if directory is None and args.publish:
        tag = "v" + changelog("Version").split("-")[0]
        existing = subprocess.run(
            [
                "gh",
                "release",
                "view",
                tag,
                "--repo",
                settings["github_repository"],
                "--json",
                "assets",
            ],
            capture_output=True,
            text=True,
        )
        if existing.returncode == 0:
            directory = ROOT / "dist/releases" / tag.removeprefix("v")
            directory.mkdir(parents=True, exist_ok=True)
            if not any(directory.iterdir()):
                run(
                    "gh",
                    "release",
                    "download",
                    tag,
                    "--repo",
                    settings["github_repository"],
                    "--dir",
                    directory,
                )
    if directory is None:
        directory = build_release(settings, env)
    manifest = verify_release(directory, settings, env)
    if not args.publish:
        print(f"Validated release: {directory}", flush=True)
        return
    if (
        manifest["dirty"]
        or manifest["commit"] != run("git", "rev-parse", "HEAD", cwd=ROOT, capture=True).strip()
    ):
        raise ValueError("Prepared artifacts must come from this clean commit")
    tag = "v" + manifest["upstream"]
    if run("git", "rev-parse", tag + "^{}", cwd=ROOT, capture=True).strip() != manifest["commit"]:
        raise ValueError("Version tag must point to the prepared commit")
    run("gpg", "--batch", "--import", ROOT / "provenance/signer.asc", env=env)
    run("git", "verify-tag", tag, cwd=ROOT, env=env)
    publish_github(directory, manifest, settings)
    upload_launchpad(directory, manifest, settings, env)
    publish_apt(directory, settings, env)
    run("gh", "release", "edit", tag, "--repo", settings["github_repository"], "--draft=false")
    print(f"Published {tag}: GitHub Releases and {settings['apt_url']}; source submitted to Launchpad", flush=True)
    wait_launchpad(settings, manifest["version"], args.wait_seconds)
    print(f"Published {tag}: GitHub Releases, Launchpad PPA and {settings['apt_url']}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Upload source packages and wait for Launchpad publication."""

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from apt_repo import run, sha256

import release_context as context
from release_artifacts import source_uploads

def launchpad_json(url):
    """Read Launchpad JSON with bounded retries for temporary network failures."""
    request = urllib.request.Request(
        url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            error.close()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
        print(f"Retrying Launchpad API request ({attempt + 2}/3)", flush=True)
        time.sleep(5 * (attempt + 1))


def launchpad_sources(settings, version, status=None):
    base = (
        f"https://api.launchpad.net/1.0/~{settings['launchpad_owner']}"
        f"/+archive/ubuntu/{settings['launchpad_archive']}"
    )
    query = {
        "ws.op": "getPublishedSources",
        "source_name": context.PACKAGE,
        "exact_match": "true",
        "version": version,
    }
    if status:
        query["status"] = status
    if settings.get("suite"):
        query["distro_series"] = f"https://api.launchpad.net/1.0/ubuntu/{settings['suite']}"
    return launchpad_json(base + "?" + urllib.parse.urlencode(query))["entries"]


def upload_launchpad(directory, manifest, settings, env):
    for upload in source_uploads(manifest):
        target_settings = settings | {"suite": upload["suite"]}
        upload_launchpad_source(directory, upload, target_settings, env)


def upload_launchpad_source(directory, upload, settings, env):
    if launchpad_sources(settings, upload["version"]) or launchpad_sources(settings, upload["version"], "Pending"):
        print(f"Launchpad already has {upload['suite']} source {upload['version']}", flush=True)
        return
    changes = directory / upload["changes"]
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
        for attempt in range(3):
            try:
                output = run(
                    "dput", "-P", "-U",
                    f"ppa:{settings['launchpad_owner']}/{settings['launchpad_archive']}",
                    changes, cwd=directory, env=env, capture=True,
                )
                print(output, end="", flush=True)
                break
            except subprocess.CalledProcessError as error:
                output = error.stdout or ""
                print(output, end="", flush=True)
                transient = re.search(
                    r"internal server error|timed out|connection (reset|refused)|"
                    r"temporary failure|\b(421|425|426|450|451|452)\b", output, re.I,
                )
                if not transient or attempt == 2:
                    raise
                print(f"Retrying Launchpad upload for {upload['suite']}", flush=True)
                time.sleep(15 * (attempt + 1))
                if launchpad_sources(settings, upload["version"]) or launchpad_sources(settings, upload["version"], "Pending"):
                    break
        print(f"Source submitted for {upload['suite']}; Launchpad acceptance/build is pending", flush=True)
        return
    if transport != "sftp":
        raise ValueError("Launchpad transport must be ftp or sftp")
    identity = Path(os.environ.get("LAUNCHPAD_SSH_KEY", context.STATE / "launchpad-upload"))
    if not identity.is_file():
        raise ValueError("LAUNCHPAD_SSH_KEY must point to the registered upload key")
    upload_sftp([*files, changes], settings, identity)
    print(f"Source uploaded for {upload['suite']}; Launchpad still needs to accept and build it", flush=True)


def upload_sftp(files, settings, identity):
    import paramiko

    incoming = f"~{settings['launchpad_owner']}/ubuntu/{settings['launchpad_archive']}"
    with paramiko.SSHClient() as client:
        client.load_host_keys(str(context.ROOT / "packaging/launchpad-known-hosts"))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(
            "ppa.launchpad.net", username=settings["launchpad_owner"],
            key_filename=str(identity), allow_agent=False, look_for_keys=False,
            timeout=15, auth_timeout=15, banner_timeout=15,
        )
        with client.open_sftp() as remote:
            remote.get_channel().settimeout(120)
            for file in files:
                with file.open("rb") as source, remote.open(f"{incoming}/{file.name}", "wb") as target:
                    shutil.copyfileobj(source, target, 128 * 1024)
                print(f"Uploaded {file.name}", flush=True)


def launchpad_binaries(source, settings):
    binaries = launchpad_json(source["self_link"] + "?ws.op=getPublishedBinaries")["entries"]
    architecture = f"/{settings['suite']}/{settings['architecture']}"
    return [
        binary
        for binary in binaries
        if binary["binary_package_name"] == context.PACKAGE
        and binary["binary_package_version"] == source["source_package_version"]
        and binary["distro_arch_series_link"].endswith(architecture)
    ]


def launchpad_binary_published(source, settings):
    return any(binary["status"] == "Published" for binary in launchpad_binaries(source, settings))


def wait_launchpad(settings, version, timeout):
    if timeout <= 0:
        raise ValueError("Launchpad stage timeout must be positive")
    deadline = time.monotonic() + timeout
    stage = -1
    labels = ("source acceptance", "build queue", "build", "binary import", "binary publication")
    while time.monotonic() < deadline:
        progress = 0
        sources = launchpad_sources(settings, version) or launchpad_sources(settings, version, "Pending")
        for source in sources:
            progress = max(progress, 1)
            builds = launchpad_json(source["self_link"] + "?ws.op=getBuilds")["entries"]
            statuses = {build["buildstate"] for build in builds}
            if statuses & {
                "Failed to build",
                "Dependency wait",
                "Chroot problem",
                "Failed to upload",
            }:
                raise ValueError("Launchpad build needs attention: " + ", ".join(sorted(statuses)))
            if "Currently building" in statuses:
                progress = max(progress, 2)
            if builds and statuses == {"Successfully built"}:
                progress = max(progress, 3)
                binaries = launchpad_binaries(source, settings)
                if binaries:
                    progress = max(progress, 4)
                if source["status"] == "Published" and any(
                    binary["status"] == "Published" for binary in binaries
                ):
                    print(f"Launchpad {settings['suite']} binary published", flush=True)
                    return
        if progress > stage:
            stage = progress
            deadline = time.monotonic() + timeout
            print(f"Waiting for Launchpad {labels[stage]} [{settings.get('suite', '')}] (up to {timeout}s)", flush=True)
        time.sleep(min(30, max(0, deadline - time.monotonic())))
    raise ValueError(
        f"Launchpad {labels[stage]} pending; resume with the same --prepared directory"
    )

#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Create signed APT indices and AppStream data without replacing package history."""

import copy
import gzip
import hashlib
import os
import pwd
import shutil
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from catalog import add_legacy_developer

ROOT = Path(__file__).resolve().parent.parent


def run(*args, cwd=None, env=None, capture=False):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        env=env,
        check=True,
        stdout=subprocess.PIPE if capture else None,
        text=capture,
    ).stdout


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def immutable_copy(source, destination):
    if destination.exists():
        if sha256(source) != sha256(destination):
            raise ValueError(f"Published artifact cannot be replaced: {destination.name}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def compressed(path):
    path.with_name(path.name + ".gz").write_bytes(gzip.compress(path.read_bytes(), mtime=0))


def compose(deb, output, config):
    with tempfile.TemporaryDirectory(prefix="dock-folders-appstream-") as temporary:
        temporary = Path(temporary)
        stage = temporary / "stage"
        run("dpkg-deb", "--extract", deb, stage)
        catalog = temporary / "catalog"
        icons = temporary / "icons"
        origin = f"hawkab-{config['suite']}-main"
        run(
            "appstreamcli",
            "compose",
            "--no-net",
            "--origin",
            origin,
            "--data-dir",
            catalog,
            "--icons-dir",
            icons,
            "--hints-dir",
            temporary / "hints",
            "--print-report=short",
            stage,
        )
        xml = ET.fromstring(gzip.decompress(next(catalog.glob("*.xml.gz")).read_bytes()))
        xml.set("origin", origin)
        metadata = ET.parse(
            stage / "usr/share/metainfo/io.github.hawkab.UbuntuDockFolders.metainfo.xml"
        ).getroot()
        for component in xml.findall("component"):
            if component.find("pkgname") is None:
                ET.SubElement(component, "pkgname").text = "ubuntu-dock-folders"
            add_legacy_developer(component)
            for icon in metadata.findall("icon[@type='remote']"):
                component.append(copy.deepcopy(icon))
        tree = temporary / "catalog.xml"
        ET.ElementTree(xml).write(tree, encoding="utf-8", xml_declaration=True)
        catalog_yaml = output / f"Components-{config['architecture']}.yml"
        run("appstreamcli", "convert", tree, catalog_yaml)
        documents = list(yaml.safe_load_all(catalog_yaml.read_text()))
        for document in documents:
            developer = document.get("Developer")
            if developer:
                document["DeveloperName"] = developer["name"]
        catalog_yaml.write_text(
            yaml.safe_dump_all(documents, allow_unicode=True, sort_keys=False, explicit_start=True)
        )
        compressed(catalog_yaml)
        public_icon = output.parents[3] / "icons/io.github.hawkab.UbuntuDockFolders.png"
        public_icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            stage / "usr/share/icons/hicolor/256x256/apps/io.github.hawkab.UbuntuDockFolders.png",
            public_icon,
        )
        for size in ("48x48", "64x64", "64x64@2", "128x128", "128x128@2"):
            directory = icons / size
            if not directory.exists():
                continue
            archive_path = output / f"icons-{size}.tar"
            with tarfile.open(archive_path, "w") as archive:
                for icon in sorted(directory.iterdir()):
                    info = archive.gettarinfo(icon, arcname=icon.name)
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    with icon.open("rb") as stream:
                        archive.addfile(info, stream)
            compressed(archive_path)


def update_archive(deb, destination, config, env=None):
    destination = Path(destination)
    pool = destination / "pool/main/u/ubuntu-dock-folders"
    immutable_copy(deb, pool / deb.name)
    dist = destination / "dists" / config["suite"]
    binary = dist / "main" / f"binary-{config['architecture']}"
    appstream = dist / "main/dep11"
    binary.mkdir(parents=True, exist_ok=True)
    appstream.mkdir(parents=True, exist_ok=True)
    packages = binary / "Packages"
    packages.write_text(run("apt-ftparchive", "packages", "pool", cwd=destination, capture=True))
    compressed(packages)
    compose(deb, appstream, config)
    for directory in (binary, appstream):
        for index in directory.iterdir():
            if not index.is_file():
                continue
            immutable_copy(index, directory / "by-hash/SHA256" / sha256(index))
        for cached in (directory / "by-hash/SHA256").iterdir():
            with cached.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha512").hexdigest()
            immutable_copy(cached, directory / "by-hash/SHA512" / digest)
    public_key = ROOT / "packaging/archive-key.asc"
    shutil.copy2(public_key, destination / "archive-key.asc")
    run(
        "gpg",
        "--batch",
        "--yes",
        "--dearmor",
        "--output",
        destination / "archive-key.gpg",
        public_key,
    )
    source = (
        f"Types: deb\nURIs: {config['apt_url']}\nSuites: {config['suite']}\n"
        f"Components: main\nArchitectures: {config['architecture']}\n"
        "Signed-By: /etc/apt/keyrings/hawkab-archive-keyring.gpg\n"
    )
    (destination / "hawkab.sources").write_text(source)
    (destination / ".nojekyll").touch()
    (destination / "index.html").write_text((ROOT / "packaging/apt-index.html").read_text())
    options = {
        "Origin": "hawkab",
        "Label": "hawkab Ubuntu packages",
        "Suite": config["suite"],
        "Codename": config["suite"],
        "Architectures": config["architecture"],
        "Components": "main",
        "Acquire-By-Hash": "yes",
        "Description": "Ubuntu Dock Folders for Ubuntu 24.04 and 26.04",
    }
    arguments = [
        part
        for key, value in options.items()
        for part in ("-o", f"APT::FTPArchive::Release::{key}={value}")
    ]
    release = run(
        "apt-ftparchive",
        *arguments,
        "release",
        f"dists/{config['suite']}",
        cwd=destination,
        capture=True,
    )
    (dist / "Release").write_text(release)
    for output, mode in (("InRelease", "--clearsign"), ("Release.gpg", "--detach-sign")):
        run(
            "gpg",
            "--batch",
            "--yes",
            "--local-user",
            config["signing_fingerprint"],
            "--digest-algo",
            "SHA256",
            "--armor",
            "--output",
            dist / output,
            mode,
            dist / "Release",
            env=env,
        )
    verify_archive(destination, config)


def verify_archive(destination, config):
    with tempfile.TemporaryDirectory(prefix="dock-folders-apt-test-") as temporary:
        temporary = Path(temporary)
        for path in ("lists/partial", "cache/archives/partial", "sourceparts"):
            (temporary / path).mkdir(parents=True)
        (temporary / "status").touch()
        key = (destination / "archive-key.gpg").resolve()
        (temporary / "sources.list").write_text(
            f"deb [signed-by={key} arch={config['architecture']}] "
            f"{destination.resolve().as_uri()} {config['suite']} main\n"
        )
        options = [
            part
            for key, value in {
                "Dir::Etc::sourcelist": temporary / "sources.list",
                "Dir::Etc::sourceparts": temporary / "sourceparts",
                "Dir::State::lists": temporary / "lists",
                "Dir::State::status": temporary / "status",
                "Dir::Cache": temporary / "cache",
                "APT::Get::List-Cleanup": "0",
                "APT::Sandbox::User": pwd.getpwuid(os.getuid()).pw_name,
                "APT::Update::Error-Mode": "any",
                "Acquire::IndexTargets::deb::DEP-11::MetaKey": "$(COMPONENT)/dep11/Components-$(NATIVE_ARCHITECTURE).yml",
                "Acquire::IndexTargets::deb::DEP-11::ShortDescription": "AppStream",
                "Acquire::IndexTargets::deb::DEP-11::Description": "AppStream catalog",
                "Acquire::IndexTargets::deb::DEP-11::DefaultEnabled": "true",
            }.items()
            for part in ("-o", f"{key}={value}")
        ]
        run("apt-get", *options, "update")
        policy = run("apt-cache", *options, "policy", "ubuntu-dock-folders", capture=True)
        if "Candidate: (none)" in policy or "Candidate:" not in policy:
            raise ValueError("APT cannot find a signed package candidate")
        if not list((temporary / "lists").glob("*Components*")):
            raise ValueError("APT did not fetch the AppStream catalog")
        print(policy, flush=True)

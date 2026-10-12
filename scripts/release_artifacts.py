# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Build and verify signed binary and source artifacts."""

import json
import re
import shutil
import tempfile
from pathlib import Path

from apt_repo import run, sha256
from catalog import verify_local_media

import release_context as context
from release_binaries import checked, package_fields


def configure_source(source, suite, version, env):
    """Use the selected source's builder rather than the publisher's metadata."""
    builder = source / "scripts/debian_target.py"
    if not builder.is_file():
        raise ValueError("Release source must include the suite-specific Debian builder.")
    run("/usr/bin/python3", builder, "configure", "--suite", suite, "--version", version, cwd=source, env=env)

def build_source(source, target, output, settings, env):
    configure_source(source, target["suite"], target["version"], env)
    run("dpkg-buildpackage", "-S", "-d", "-sa", "-us", "-uc", cwd=source, env=env)
    changes = source.parent / f"{context.PACKAGE}_{target['version']}_source.changes"
    run("debsign", "--no-re-sign", "-k" + settings["signing_fingerprint"], changes, env=env)
    for pattern in ("*.dsc", "*.tar.xz", "*_source.changes", "*_source.buildinfo"):
        for artifact in source.parent.glob(pattern):
            destination = output / artifact.name
            if destination.exists() and sha256(destination) != sha256(artifact):
                raise ValueError(f"Source artifact collision: {artifact.name}")
            shutil.copy2(artifact, destination)
    return target | {"changes": changes.name}


def source_uploads(manifest):
    uploads = manifest.get("launchpad", [{
        "suite": manifest["suite"],
        "version": manifest["version"],
        "changes": f"{context.PACKAGE}_{manifest['version']}_source.changes",
    }])
    for upload in uploads:
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]*", upload["suite"])
            or not re.fullmatch(r"[0-9A-Za-z.-]+", upload["version"])
            or upload["version"].split("-")[0] != manifest["upstream"]
            or upload["changes"] != f"{context.PACKAGE}_{upload['version']}_source.changes"
        ):
            raise ValueError("Invalid Launchpad source manifest")
    if (
        not uploads
        or len({upload["suite"] for upload in uploads}) != len(uploads)
        or len({upload["version"] for upload in uploads}) != len(uploads)
    ):
        raise ValueError("Invalid Launchpad source targets")
    return uploads


def build_release(settings, env, binaries=None):
    version = context.changelog("Version")
    if not re.fullmatch(r"[0-9A-Za-z.-]+", version):
        raise ValueError(
            "Use an APT version with GitHub-safe filenames, for example 1.1.1-1ubuntu24.04.1"
        )
    upstream = version.split("-")[0]
    if not re.fullmatch(r"\d+\.\d+\.\d+", upstream):
        raise ValueError("Release version must use major.minor.patch")
    if context.changelog("Distribution") != settings["suite"]:
        raise ValueError("Changelog suite differs from release configuration")
    if run("dpkg", "--print-architecture", capture=True).strip() != settings["architecture"]:
        raise ValueError("Build architecture differs from release configuration")
    context.validate_build_series(settings)
    targets = context.launchpad_targets(settings, version)
    commit = run("git", "rev-parse", "HEAD", cwd=context.ROOT, capture=True).strip()
    bundles = checked(binaries, targets, settings["architecture"], commit) if binaries else None
    output = context.ROOT / "dist/releases" / upstream
    if output.exists():
        raise ValueError(f"{output} already exists; use --prepared to resume it or move it aside")
    output.mkdir(parents=True)
    env = env | {"SOURCE_DATE_EPOCH": context.changelog("Timestamp")}
    with tempfile.TemporaryDirectory(prefix="dock-folders-release-") as temporary:
        temporary = Path(temporary)
        source = temporary / f"{context.PACKAGE}-{upstream}"
        context.snapshot(source)
        orig = temporary / f"{context.PACKAGE}_{upstream}.orig.tar.xz"
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
        configure_source(source, settings["suite"], version, env)
        if bundles:
            for suite, (bundle, directory) in bundles.items():
                shutil.copy2(directory / bundle["package"], output / bundle["package"])
                if suite == settings["suite"]:
                    for name in bundle["files"]:
                        if name.endswith(".zip"):
                            shutil.copy2(directory / name, output / name)
        else:
            run("dpkg-buildpackage", "-b", "-us", "-uc", cwd=source, env=env)
            for file in source.glob("dist/*.zip"):
                shutil.copy2(file, output / file.name)
            for file in temporary.glob("*.deb"):
                shutil.copy2(file, output / file.name)
        uploads = []
        for target in targets:
            target_source = source
            if target["suite"] != settings["suite"]:
                parent = temporary / target["suite"]
                parent.mkdir()
                target_source = parent / source.name
                context.snapshot(target_source)
                shutil.copy2(orig, parent / orig.name)
            uploads.append(build_source(target_source, target, output, settings, env))
        for dsc in output.glob("*.dsc"):
            with tempfile.TemporaryDirectory(prefix="dock-folders-unpack-") as unpack:
                run("dpkg-source", "--no-check", "-x", dsc, Path(unpack) / "source")
    shutil.copy2(context.ROOT / "packaging/archive-key.asc", output / "archive-key.asc")
    manifest = {
        "version": version,
        "upstream": upstream,
        "suite": settings["suite"],
        "architecture": settings["architecture"],
        "launchpad": uploads,
        "commit": commit,
        "dirty": bool(run("git", "status", "--porcelain", cwd=context.ROOT, capture=True).strip()),
        "files": {file.name: sha256(file) for file in sorted(output.iterdir()) if file.is_file()},
    }
    manifest["binaries"] = [{"suite": target["suite"], "version": target["version"],
        "file": f"{context.PACKAGE}_{target['version']}_{settings['architecture']}.deb"}
        for target in targets if bundles or target["suite"] == settings["suite"]]
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
    if manifest.get("version") != context.changelog("Version"):
        raise ValueError("Prepared version differs from the changelog")
    if manifest.get("upstream") != manifest["version"].split("-")[0]:
        raise ValueError("Prepared upstream version differs from the package version")
    for field in ("suite", "architecture"):
        if manifest[field] != settings[field]:
            raise ValueError(f"Release {field} differs from current configuration")
    for source in list(directory.glob("*.dsc")) + list(directory.glob("*_source.changes")):
        run("gpg", "--verify", source, env=env)
    for upload in source_uploads(manifest):
        changes = directory / upload["changes"]
        if upload["changes"] not in manifest["files"]:
            raise ValueError("Launchpad upload is missing from the release manifest")
        text = run("gpg", "--batch", "--decrypt", changes, env=env, capture=True)
        for field, value in (("Distribution", upload["suite"]), ("Version", upload["version"])):
            if not re.search(rf"^{field}: {re.escape(value)}$", text, re.MULTILINE):
                raise ValueError(f"Source upload {field} differs from its manifest")
        run("dput", "-o", changes, cwd=directory, env=env)
    for binary in manifest.get("binaries", [{"suite": manifest["suite"], "version": manifest["version"],
            "file": next(directory.glob("*.deb")).name}]):
        name = f"{context.PACKAGE}_{binary['version']}_{settings['architecture']}.deb"
        if binary["file"] != name or name not in manifest["files"]:
            raise ValueError("Release binary differs from its manifest")
        package = directory / name
        if package_fields(package) != (context.PACKAGE, binary["version"], settings["architecture"]):
            raise ValueError("Release binary metadata differs from its manifest")
        verify_local_media(package)
    return manifest

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Record checked packages and verify their commit, suite and checksums."""

import argparse
import json
import shutil
from pathlib import Path

from apt_repo import run, sha256
import release_context as context


def package_fields(file):
    return tuple(run("dpkg-deb", "-f", file, field, capture=True).strip()
                 for field in ("Package", "Version", "Architecture"))


def record(suite, destination):
    version = context.changelog("Version")
    architecture = run("dpkg", "--print-architecture", capture=True).strip()
    if context.changelog("Distribution") != suite:
        raise ValueError("Checked package suite differs from the changelog")
    filename = f"{context.PACKAGE}_{version}_{architecture}.deb"
    package = context.ROOT.parent / filename
    if package_fields(package) != (context.PACKAGE, version, architecture):
        raise ValueError("Checked package metadata differs from the build target")
    destination.mkdir(parents=True, exist_ok=True)
    files = [package, *sorted((context.ROOT / "dist").glob("*.zip"))]
    for file in files:
        shutil.copy2(file, destination / file.name)
    manifest = {
        "commit": run("git", "rev-parse", "HEAD", cwd=context.ROOT, capture=True).strip(),
        "suite": suite, "version": version, "architecture": architecture,
        "package": filename, "files": {file.name: sha256(file) for file in files},
    }
    (destination / "binary.json").write_text(json.dumps(manifest, indent=2) + "\n")


def checked(directory, targets, architecture, commit):
    """Return verified build bundles; require exactly one package per target suite."""
    expected = {target["suite"]: target["version"] for target in targets}
    result = {}
    for file in directory.rglob("binary.json"):
        manifest = json.loads(file.read_text())
        suite, version = manifest["suite"], manifest["version"]
        if (suite not in expected or expected[suite] != version or suite in result
                or manifest["commit"] != commit or manifest["architecture"] != architecture):
            raise ValueError("Checked binary has an unexpected commit, suite or version")
        name = f"{context.PACKAGE}_{version}_{architecture}.deb"
        if manifest["package"] != name or name not in manifest["files"]:
            raise ValueError("Checked package filename differs from its build target")
        for name, digest in manifest["files"].items():
            artifact = file.parent / name
            if (Path(name).name != name or artifact.is_symlink() or not artifact.is_file()
                    or sha256(artifact) != digest):
                raise ValueError("Checked binary checksum mismatch")
        package = file.parent / manifest["package"]
        if package_fields(package) != (context.PACKAGE, version, architecture):
            raise ValueError("Checked package metadata differs from its manifest")
        result[suite] = (manifest, file.parent)
    if set(result) != set(expected):
        raise ValueError("Checked binaries must include every supported Ubuntu suite")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    record(args.suite, args.output)


if __name__ == "__main__":
    main()

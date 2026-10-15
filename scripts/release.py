# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Build, validate, and publish a reviewed release."""

import argparse
import subprocess
from pathlib import Path

from apt_repo import run

import release_context as context
from release_artifacts import source_uploads, build_release, verify_release
from launchpad_publish import upload_launchpad, wait_launchpad
from release_publish import publish_apt, publish_github

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--binaries", type=Path, help="Checked CI packages for all supported Ubuntu suites")
    parser.add_argument("--source-root", type=Path, default=context.ROOT, help="Clean checkout of the signed release tag")
    args = parser.parse_args()
    context.ROOT = args.source_root.resolve()
    settings = context.config()
    env = context.signing_environment()
    if args.publish and run("git", "status", "--porcelain", cwd=context.ROOT, capture=True).strip():
        raise ValueError("Commit reviewed changes before publishing")
    directory = args.prepared.resolve() if args.prepared else None
    if directory is None and args.publish:
        tag = "v" + context.changelog("Version").split("-")[0]
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
            directory = context.ROOT / "dist/releases" / tag.removeprefix("v")
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
        directory = build_release(settings, env, args.binaries)
    manifest = verify_release(directory, settings, env)
    if not args.publish:
        print(f"Validated release: {directory}", flush=True)
        return
    targets = context.launchpad_targets(settings, manifest["version"])
    if sorted((item["suite"], item["version"]) for item in manifest.get("binaries", [])) != sorted(
            (item["suite"], item["version"]) for item in targets):
        raise ValueError("Publish checked binaries for every supported Ubuntu suite with --binaries")
    if (
        manifest["dirty"]
        or manifest["commit"] != run("git", "rev-parse", "HEAD", cwd=context.ROOT, capture=True).strip()
    ):
        raise ValueError("Prepared artifacts must come from this clean commit")
    tag = "v" + manifest["upstream"]
    if run("git", "rev-parse", tag + "^{}", cwd=context.ROOT, capture=True).strip() != manifest["commit"]:
        raise ValueError("Version tag must point to the prepared commit")
    run("gpg", "--batch", "--import", context.ROOT / "provenance/signer.asc", env=env)
    run("git", "verify-tag", tag, cwd=context.ROOT, env=env)
    publish_github(directory, manifest, settings)
    upload_launchpad(directory, manifest, settings, env)
    publish_apt(directory, settings, env)
    run("gh", "release", "edit", tag, "--repo", settings["github_repository"], "--draft=false")
    print(f"Published {tag}: GitHub Releases and {settings['apt_url']}; source submitted to Launchpad", flush=True)
    for upload in source_uploads(manifest):
        wait_launchpad(settings | {"suite": upload["suite"]}, upload["version"])
    print(f"Published {tag}: GitHub Releases, Launchpad PPA and {settings['apt_url']}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error

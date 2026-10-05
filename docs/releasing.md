# Release publication

Ubuntu 24.04 (`noble`), GNOME 46 and amd64 are the supported target. The Debian version in `debian/changelog` is shared by the PPA, GitHub Releases and the signed [APT repository](https://hawkab.github.io/apt/). The PPA builds its binary on Launchpad; the other channels use the locally tested binary.

## Publish

Update `debian/changelog`, the AppStream release entry and the extension metadata version. Commit the reviewed changes and create a version tag:

```sh
git tag -s v1.0.1 -m 'Ubuntu Dock Folders 1.0.1'
git push origin main v1.0.1
```

The `Release` workflow runs the Debian build and test suite, signs the source package and checksums, uploads a draft GitHub release, submits the signed source through `dput` to Launchpad and waits for its build. After a successful build, it publishes APT indices and makes the GitHub release public. Run the workflow manually with the same tag to resume an interrupted publication.

The same pipeline runs locally:

```sh
sudo apt install build-essential debhelper devscripts dput apt-utils appstream-compose desktop-file-utils gettext libglib2.0-dev librsvg2-common pkg-config gnome-shell gnome-shell-extension-ubuntu-dock python3-gi python3-pil python3-cairo python3-gi-cairo python3-yaml gir1.2-gtk-4.0 gir1.2-gdkpixbuf-2.0 gir1.2-adw-1 nodejs dbus-daemon xvfb xauth gh
python3 scripts/release.py
python3 scripts/release.py --publish --prepared dist/releases/1.0.1
```

Preparation alone builds, tests and signs without publishing. Publication requires a clean commit and a matching version tag. A previously published file cannot be replaced with different contents; bump the Debian version for packaging changes and the upstream version for a new release. A Launchpad timeout leaves the draft and signed artifacts available for resuming.

## Credentials and repository settings

Public destinations and the signing fingerprint are in `packaging/release.toml`. SSH host keys are pinned in `packaging/*-known-hosts`; Launchpad's RSA fingerprint follows its [official list](https://ubuntu.com/docs/launchpad/user/reference/ssh-fingerprints/), GitHub's keys follow the [Meta API](https://api.github.com/meta).

The GitHub `release` environment uses three secrets:

| Secret | Scope |
| --- | --- |
| `RELEASE_GPG_KEY` | Dedicated release signing key; registered and verified on Launchpad |
| `LAUNCHPAD_UPLOAD_KEY` | Dedicated SSH key registered on the Launchpad account for SFTP uploads |
| `APT_DEPLOY_KEY` | Write deploy key for `hawkab/apt` only |

GitHub Releases uses the workflow's short-lived `GITHUB_TOKEN`. The APT repository publishes Pages from `main` at `/`, with `.nojekyll`. Its signed `InRelease`, package hashes and AppStream catalog are checked using an isolated APT client before pushing. Packages and `by-hash` indices are retained for clients downloading an older index.

The default Launchpad transport is FTP for public, signed source artifacts. Set `LAUNCHPAD_UPLOAD_TRANSPORT=sftp` to use the registered SSH key instead.

Local publishing reads `GNUPGHOME`, `LAUNCHPAD_SSH_KEY` and `APT_DEPLOY_KEY`. If unset, it uses the private publishing directory under `$XDG_STATE_HOME/ubuntu-dock-folders/publishing` (default `~/.local/state`). Never commit private keys. The archive key expires on 4 October 2029; renew it and update both the local keyring and CI secret before expiry.

# Release publication

Ubuntu 24.04 (`noble`) / GNOME 46 and Ubuntu 26.04 (`resolute`) / GNOME 50 are the supported runtimes on amd64. Build the release binary on Ubuntu 24.04 and test it on both runtimes. The Launchpad publication target remains `noble`; a `resolute` PPA requires a separate source upload. Use a Debian version such as `1.1.0-1ubuntu24.04.1`; `~` is excluded because GitHub renames it in asset filenames. The Debian version in `debian/changelog` is shared by the PPA, GitHub Releases and the signed [APT repository](https://hawkab.github.io/apt/). The PPA builds its binary on Launchpad; the other channels use the locally tested binary.

## Publish

`make test-shell` checks grouping, both animations, glass blur, running indicators, window previews, reordering, extraction, undo and extension cleanup in a private headless GNOME Shell. It uses temporary settings, a private D-Bus session and software rendering. The `Check` workflow runs the package and Shell checks on Ubuntu 24.04 and 26.04.

Run `xvfb-run -a python3 scripts/test_shell.py --client-backend x11` to check Xwayland applications. On GNOME 46, also run `xvfb-run -a python3 scripts/test_shell.py --backend x11` for a native X11 session. GNOME 50 no longer provides the X11 session backend. The package tests also remove the companion while the actual Ubuntu Settings panel and its folder dialog are open.

Update `debian/changelog`, the AppStream release entry and the extension metadata version. Commit the reviewed changes and create a version tag:

```sh
git tag -s v1.0.3 -m 'Ubuntu Dock Folders 1.0.3'
git push origin main v1.0.3
```

The `Release` workflow runs the Debian build and test suite, signs the source package and checksums, uploads a draft GitHub release and submits the signed source through `dput` to Launchpad. It publishes the APT indices and GitHub release, then waits for Launchpad's acceptance, build queue, build, binary import and publication. Each stage has up to an hour; advancing to the next stage resets the timeout. A stalled stage or failed build fails the workflow. A delayed PPA build does not hold back the other channels. Run the workflow manually with the same tag to resume an interrupted publication.

Manual runs from `main` use its current publisher with a separate checkout of the requested signed tag. This applies publishing fixes to an existing release without rebuilding or replacing its artifacts. The equivalent local option is `--source-root PATH`, pointing to a clean checkout of that tag.

The same pipeline runs locally:

```sh
sudo apt install build-essential debhelper devscripts dput apt-utils appstream-compose desktop-file-utils gettext git gnupg locales-all libglib2.0-dev librsvg2-common pkg-config gnome-shell gnome-shell-extension-ubuntu-dock gnome-control-center dconf-cli python3-gi python3-pil python3-cairo python3-gi-cairo python3-yaml gir1.2-gtk-4.0 gir1.2-gdkpixbuf-2.0 gir1.2-adw-1 nodejs dbus-daemon xvfb xauth xwayland gh
python3 scripts/release.py
python3 scripts/release.py --publish --prepared dist/releases/1.0.3
```

Preparation alone builds, tests and signs without publishing. Publication requires a clean commit and a matching version tag. A previously published file cannot be replaced with different contents; use a new upstream version and corresponding Debian version for each publication. A Launchpad timeout leaves the public APT and GitHub artifacts available; resuming checks the PPA state without replacing published files.

## Credentials and repository settings

Public destinations and the signing fingerprint are in `packaging/release.toml`. SSH host keys are pinned in `packaging/*-known-hosts`; Launchpad's RSA fingerprint follows its [official list](https://ubuntu.com/docs/launchpad/user/reference/ssh-fingerprints/), GitHub's keys follow the [Meta API](https://api.github.com/meta).

The GitHub `release` environment accepts version tags matching `v*` and manual runs from `main`. It uses three secrets:

| Secret | Scope |
| --- | --- |
| `RELEASE_GPG_KEY` | Dedicated release signing key; registered and verified on Launchpad |
| `LAUNCHPAD_UPLOAD_KEY` | Dedicated SSH key registered on the Launchpad account for SFTP uploads |
| `APT_DEPLOY_KEY` | Write deploy key for `hawkab/apt` only |

GitHub Releases uses the workflow's short-lived `GITHUB_TOKEN`. The APT repository publishes Pages from `main` at `/`, with `.nojekyll`. Its signed `InRelease`, package hashes and AppStream catalog are checked using an isolated APT client before pushing. Packages and `by-hash` indices are retained for clients downloading an older index.

The default Launchpad transport is FTP for public, signed source artifacts. Set `LAUNCHPAD_UPLOAD_TRANSPORT=sftp` to use the registered SSH key instead.

Local publishing reads `GNUPGHOME`, `LAUNCHPAD_SSH_KEY` and `APT_DEPLOY_KEY`. If unset, it uses the private publishing directory under `$XDG_STATE_HOME/ubuntu-dock-folders/publishing` (default `~/.local/state`). Never commit private keys. The archive key expires on 4 October 2029; renew it and update both the local keyring and CI secret before expiry.

# Flathub Submission Notes

## Current Packaging Decisions

- App ID: `io.github.saleguas.librewolfprofiles`
- Runtime: `org.gnome.Platform//48`
- SDK: `org.gnome.Sdk//48`
- Command: `io.github.saleguas.librewolfprofiles`

## Why `org.freedesktop.Flatpak` access is requested

The app's job is to launch the installed LibreWolf Flatpak with profile-specific arguments such as `-P <profile>` and `--ProfileManager`. Inside a Flatpak sandbox, that requires host-side Flatpak access via `flatpak-spawn --host`.

Flathub documents `--talk-name=org.freedesktop.Flatpak` as a restricted permission that is granted case-by-case when no portal-based alternative exists.

Sources:

- https://docs.flathub.org/docs/for-app-authors/linter
- https://docs.flatpak.org/en/latest/flatpak-command-reference.html

## Before Submission

- Ensure `docs/image.png` is published at the GitHub URL referenced in the metainfo file, or replace it with a commit-pinned screenshot URL before submission.
- Replace `LicenseRef-proprietary` in the metainfo with the actual project license.
- Run Flathub's appstream linter and a real Flatpak build on a machine that has `flatpak-builder`.
- Expect review questions about the `org.freedesktop.Flatpak` permission because the linter explicitly treats it as restricted.

## Verification

Flathub documents `io.github.` as a supported source-code-hosting application ID prefix for GitHub-backed projects. Because this repository remote is `https://github.com/saleguas/LibrewolfProfiles.git`, the chosen app ID is aligned with current Flathub guidance for GitHub-hosted apps.

Sources:

- https://docs.flathub.org/docs/for-app-authors/requirements
- https://docs.flathub.org/docs/for-app-authors/verification

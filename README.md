# LibreWolf Profiles

LibreWolf Profiles is a small launcher for the LibreWolf Flatpak that lets you:

- view the profiles registered in LibreWolf
- launch a specific profile directly
- create a new profile through LibreWolf itself
- open LibreWolf's built-in profile manager

The repo now contains two tracks:

- a repo-tracked local launcher script that preserves the current desktop workflow
- a standalone desktop app plus Flatpak metadata for packaging and Flathub submission work

## Safety

Before changing anything, the current launcher and LibreWolf profile state were backed up on this machine to:

- `/var/home/bazzite/Documents/LibrewolfProfilesBackup-20260421-205704`

The application code in this repo does not edit `profiles.ini` directly. It reads the existing profile registry and delegates profile creation and launches back to LibreWolf.

## Repo Layout

- `tools/local/librewolf-profile-launcher.sh` keeps the current shell-based launcher behavior in the repo.
- `tools/install-local-wrapper.sh` installs a tiny wrapper into `~/.local/bin/librewolf-profile-launcher` so the desktop shortcut can keep using repo-tracked code.
- `src/librewolf_profiles/` contains the desktop app source.
- `data/` contains the desktop file, metainfo, and icon.
- `io.github.saleguas.librewolfprofiles.yml` is the Flatpak manifest.
- `flatpak/screenshots/` contains the screenshot asset referenced by AppStream metadata.

## Local Wrapper

To repoint the current launcher to the repo copy:

```bash
./tools/install-local-wrapper.sh
```

This keeps the existing desktop entry path stable while moving the actual logic into this repo.

## Build

This environment does not currently provide `flatpak`, `flatpak-builder`, or `desktop-file-validate`, so the repo includes the packaging files but cannot perform a full Flatpak build here.

Meson install layout:

```bash
meson setup _build
meson compile -C _build
meson install -C _build --destdir "$(pwd)/dist"
```

Flatpak build, once the host has Flatpak tooling available:

```bash
flatpak-builder --user --force-clean ../librewolfprofiles-flatpak-build io.github.saleguas.librewolfprofiles.yml
flatpak-builder --run ../librewolfprofiles-flatpak-build io.github.saleguas.librewolfprofiles.yml io.github.saleguas.librewolfprofiles
```

## Flathub Notes

Two items still need attention before a real Flathub submission:

- replace the placeholder `project_license` value in the metainfo with the actual project license
- push the current screenshot at `docs/image.png` to a reachable URL so AppStream validation can fetch it

The manifest uses `--talk-name=org.freedesktop.Flatpak` because the app must launch the LibreWolf Flatpak from inside its own sandbox. Flathub documents this permission as restricted and reviewed case-by-case.

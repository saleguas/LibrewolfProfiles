#!/usr/bin/env bash

set -euo pipefail

librewolf_app_id="${LIBREWOLF_FLATPAK_APP_ID:-io.gitlab.librewolf-community}"
profiles_root="${LIBREWOLF_PROFILES_ROOT:-$HOME/.var/app/$librewolf_app_id/.librewolf}"
profiles_ini="${LIBREWOLF_PROFILES_INI:-$profiles_root/profiles.ini}"

if [[ ! -f "$profiles_ini" ]]; then
    kdialog --error "LibreWolf profiles file not found:\n$profiles_ini" >/dev/null 2>&1 || true
    exit 1
fi

declare -A path_by_name=()
profiles=()

while IFS=$'\t' read -r profile_name profile_path; do
    [[ -n "$profile_name" ]] || continue

    profiles+=("$profile_name")
    path_by_name["$profile_name"]="$profile_path"
done < <(
    awk '
        /^\[Profile[0-9]+\]$/ {
            if (in_profile && name != "") {
                print name "\t" path
            }
            in_profile = 1
            name = ""
            path = ""
            next
        }

        /^\[/ {
            if (in_profile && name != "") {
                print name "\t" path
            }
            in_profile = 0
            next
        }

        !in_profile {
            next
        }

        /^Name=/ {
            name = substr($0, 6)
            next
        }

        /^Path=/ {
            path = substr($0, 6)
            next
        }

        END {
            if (in_profile && name != "") {
                print name "\t" path
            }
        }
    ' "$profiles_ini"
)

if [[ ${#profiles[@]} -eq 0 ]]; then
    kdialog --error "No LibreWolf profiles were found in:\n$profiles_ini" >/dev/null 2>&1 || true
    exit 1
fi

IFS=$'\n' read -r -d '' -a sorted_profiles < <(printf '%s\n' "${profiles[@]}" | sort -f && printf '\0')

menu_args=()
menu_args+=("__create__" "Create New Profile...")
menu_args+=("__manage__" "Open Built-in Profile Manager")
for profile_name in "${sorted_profiles[@]}"; do
    menu_args+=("$profile_name" "$profile_name")
done

choice=$(
    kdialog \
        --geometry 420x560 \
        --title "LibreWolf Profiles" \
        --menu "Choose a LibreWolf profile to open" \
        "${menu_args[@]}"
) || exit 0

if [[ "$choice" == "__create__" ]]; then
    new_profile_name=$(
        kdialog \
            --title "LibreWolf Profiles" \
            --inputbox "Name for the new LibreWolf profile"
    ) || exit 0

    new_profile_name="${new_profile_name#"${new_profile_name%%[![:space:]]*}"}"
    new_profile_name="${new_profile_name%"${new_profile_name##*[![:space:]]}"}"

    if [[ -z "$new_profile_name" ]]; then
        exit 0
    fi

    if [[ -n "${path_by_name[$new_profile_name]:-}" ]]; then
        kdialog --error "A LibreWolf profile named '$new_profile_name' already exists." >/dev/null 2>&1 || true
        exit 1
    fi

    if ! flatpak run "$librewolf_app_id" -CreateProfile "$new_profile_name"; then
        kdialog --error "LibreWolf could not create the profile '$new_profile_name'." >/dev/null 2>&1 || true
        exit 1
    fi

    exec flatpak run "$librewolf_app_id" --new-instance -P "$new_profile_name"
fi

if [[ "$choice" == "__manage__" ]]; then
    exec flatpak run "$librewolf_app_id" --new-instance --ProfileManager
fi

if flatpak run "$librewolf_app_id" --new-instance -P "$choice"; then
    exit 0
fi

exec flatpak run "$librewolf_app_id" -P "$choice"

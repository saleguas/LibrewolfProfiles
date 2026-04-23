#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="$repo_root/io.github.saleguas.librewolfprofiles.yml"

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

[[ -f "$manifest" ]] || die "manifest not found: $manifest"

read_manifest_value() {
    local key="$1"
    awk -F': ' -v key="$key" '$1 == key { print $2; exit }' "$manifest"
}

strip_single_quotes() {
    local value="$1"
    value="${value#\'}"
    value="${value%\'}"
    printf '%s' "$value"
}

app_id="$(read_manifest_value app-id)"
runtime="$(read_manifest_value runtime)"
runtime_version="$(strip_single_quotes "$(read_manifest_value runtime-version)")"
sdk="$(read_manifest_value sdk)"

[[ -n "$app_id" ]] || die "could not read app-id from $manifest"
[[ -n "$runtime" ]] || die "could not read runtime from $manifest"
[[ -n "$runtime_version" ]] || die "could not read runtime-version from $manifest"
[[ -n "$sdk" ]] || die "could not read sdk from $manifest"

branch="${FLATPAK_BRANCH:-stable}"
build_dir="$repo_root/flatpak-build"
repo_dir="$repo_root/repo"
bundle_path="$repo_root/${app_id}.flatpak"
host_mode="direct"

if command -v flatpak-spawn >/dev/null 2>&1 && flatpak-spawn --host true >/dev/null 2>&1; then
    host_mode="flatpak-spawn --host"
fi

if [[ -t 1 ]] && command -v tput >/dev/null 2>&1 && [[ "$(tput colors 2>/dev/null || printf '0')" -ge 8 ]]; then
    bold="$(tput bold)"
    dim="$(tput dim)"
    red="$(tput setaf 1)"
    green="$(tput setaf 2)"
    yellow="$(tput setaf 3)"
    blue="$(tput setaf 4)"
    cyan="$(tput setaf 6)"
    reset="$(tput sgr0)"
else
    bold=""
    dim=""
    red=""
    green=""
    yellow=""
    blue=""
    cyan=""
    reset=""
fi

host_bash() {
    local script="$1"
    shift

    if [[ "$host_mode" == "flatpak-spawn --host" ]]; then
        flatpak-spawn --host bash -lc "$script" bash "$@"
    else
        bash -lc "$script" bash "$@"
    fi
}

print_banner() {
    if [[ -t 1 ]]; then
        clear
    fi

    printf '%s%s' "$bold" "$cyan"
    cat <<'EOF'
======================================================================
  LibreWolf Profiles Flatpak Helper
======================================================================
EOF
    printf '%s' "$reset"
    printf '%sApp:%s      %s\n' "$dim" "$reset" "$app_id"
    printf '%sRuntime:%s  %s//%s\n' "$dim" "$reset" "$runtime" "$runtime_version"
    printf '%sSDK:%s      %s//%s\n' "$dim" "$reset" "$sdk" "$runtime_version"
    printf '%sBranch:%s   %s\n' "$dim" "$reset" "$branch"
    printf '%sHost:%s     %s\n' "$dim" "$reset" "$host_mode"
    printf '%sRepo:%s     %s\n' "$dim" "$reset" "$repo_root"
    printf '%sBundle:%s   %s\n\n' "$dim" "$reset" "$bundle_path"
}

print_step() {
    printf '%s==>%s %s\n' "$blue" "$reset" "$1"
}

print_success() {
    printf '%s[ok]%s %s\n' "$green" "$reset" "$1"
}

print_warning() {
    printf '%s[!]%s %s\n' "$yellow" "$reset" "$1"
}

print_error() {
    printf '%s[x]%s %s\n' "$red" "$reset" "$1" >&2
}

pause_for_input() {
    [[ -t 0 ]] || return 0
    printf '\nPress Enter to continue...'
    read -r
}

require_host_tools() {
    if ! host_bash 'command -v flatpak >/dev/null 2>&1 && command -v flatpak-builder >/dev/null 2>&1'; then
        print_error "flatpak and flatpak-builder must exist on the host."
        return 1
    fi
}

prepare_host() {
    print_step "Checking host tooling"
    require_host_tools || return 1

    print_step "Ensuring the flathub remote exists"
    if ! host_bash \
        'flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo'
    then
        print_error "failed to add or verify the flathub remote on the host."
        return 1
    fi

    print_step "Installing the required runtime and SDK on the host"
    if ! host_bash \
        'flatpak install --user -y flathub "$1" "$2"' \
        "${runtime}//${runtime_version}" \
        "${sdk}//${runtime_version}"
    then
        print_error "failed to install the Flatpak runtime or SDK."
        return 1
    fi
}

install_local() {
    print_banner
    printf '%s%sInstall Locally%s\n' "$bold" "$green" "$reset"
    printf 'Builds and installs the app into your user Flatpak installation on the host.\n\n'

    prepare_host || return 1

    print_step "Building and installing the app"
    if ! host_bash \
        'cd "$1" && flatpak-builder --user --install --force-clean --default-branch="$2" "$3" "$4"' \
        "$repo_root" \
        "$branch" \
        "$build_dir" \
        "$manifest"
    then
        print_error "local Flatpak install failed."
        return 1
    fi

    printf '\n'
    print_success "installed $app_id on the host."
    print_success "launch it with: flatpak run $app_id"
}

build_bundle() {
    print_banner
    printf '%s%sBuild Flatpak File%s\n' "$bold" "$green" "$reset"
    printf 'Builds the app and exports a distributable .flatpak bundle in the repo root.\n\n'

    prepare_host || return 1

    print_step "Building the Flatpak repo export"
    if ! host_bash \
        'cd "$1" && flatpak-builder --force-clean --repo="$2" --default-branch="$3" "$4" "$5"' \
        "$repo_root" \
        "$repo_dir" \
        "$branch" \
        "$build_dir" \
        "$manifest"
    then
        print_error "Flatpak repo export failed."
        return 1
    fi

    print_step "Bundling the .flatpak file"
    if ! host_bash \
        'cd "$1" && flatpak build-bundle "$2" "$3" "$4" "$5"' \
        "$repo_root" \
        "$repo_dir" \
        "$bundle_path" \
        "$app_id" \
        "$branch"
    then
        print_error "bundle creation failed."
        return 1
    fi

    printf '\n'
    print_success "created bundle: $bundle_path"
}

usage() {
    cat <<EOF
Usage:
  $(basename "$0")            Open the interactive menu
  $(basename "$0") install    Build and install locally on the host
  $(basename "$0") bundle     Build a .flatpak bundle on the host
  $(basename "$0") help       Show this help text

Environment:
  FLATPAK_BRANCH   Override the Flatpak branch name (default: $branch)
EOF
}

run_action() {
    local action="$1"

    if "$action"; then
        pause_for_input
    else
        pause_for_input
        return 1
    fi
}

show_menu() {
    local -a options=(
        "Install locally"
        "Build .flatpak bundle"
        "Quit"
    )
    local -a descriptions=(
        "Build and install the app into your user Flatpak setup on the host."
        "Create a distributable .flatpak file in the repo root."
        "Exit without running any build commands."
    )
    local choice=0
    local key=""

    while true; do
        print_banner
        printf '%sUse arrow keys, j/k, or 1-3. Press Enter to choose.%s\n\n' "$dim" "$reset"

        for i in "${!options[@]}"; do
            if [[ "$i" -eq "$choice" ]]; then
                printf '%s%s> %s%s\n' "$bold" "$green" "${options[$i]}" "$reset"
                printf '  %s\n\n' "${descriptions[$i]}"
            else
                printf '  %s\n' "${options[$i]}"
                printf '  %s\n\n' "${descriptions[$i]}"
            fi
        done

        IFS= read -rsn1 key
        if [[ "$key" == $'\x1b' ]]; then
            IFS= read -rsn2 -t 0.05 key || true
            key=$'\x1b'"$key"
        fi

        case "$key" in
            $'\x1b[A'|k|K|w|W)
                choice=$(((choice + ${#options[@]} - 1) % ${#options[@]}))
                ;;
            $'\x1b[B'|j|J|s|S)
                choice=$(((choice + 1) % ${#options[@]}))
                ;;
            1)
                choice=0
                run_action install_local
                ;;
            2)
                choice=1
                run_action build_bundle
                ;;
            3|q|Q)
                return 0
                ;;
            "")
                case "$choice" in
                    0) run_action install_local ;;
                    1) run_action build_bundle ;;
                    2) return 0 ;;
                esac
                ;;
        esac
    done
}

case "${1:-}" in
    "" )
        show_menu
        ;;
    install )
        install_local
        ;;
    bundle )
        build_bundle
        ;;
    help|-h|--help )
        usage
        ;;
    * )
        usage
        exit 1
        ;;
esac

#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_local() {
    cd "$repo_root"
    export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"
    exec python3 -m librewolf_profiles.main "$@"
}

if [[ -f /.flatpak-info ]] && command -v flatpak-spawn >/dev/null 2>&1 && [[ -z "${LIBREWOLF_PROFILES_NO_HOST_SPAWN:-}" ]]; then
    exec flatpak-spawn --host bash -lc '
        set -euo pipefail
        cd "$1"
        export PYTHONPATH="$1/src${PYTHONPATH:+:$PYTHONPATH}"
        exec python3 -m librewolf_profiles.main "${@:2}"
    ' bash "$repo_root" "$@"
fi

run_local "$@"

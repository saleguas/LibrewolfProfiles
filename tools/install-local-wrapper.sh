#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$HOME/.local/bin/librewolf-profile-launcher"

mkdir -p "$(dirname "$target")"

tmp_file="$(mktemp)"
cat >"$tmp_file" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$repo_root/tools/local/librewolf-profile-launcher.sh" "\$@"
EOF

chmod 755 "$tmp_file"
mv "$tmp_file" "$target"

printf 'Installed wrapper: %s\n' "$target"

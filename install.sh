#!/usr/bin/env bash
# Local development install. Collector setup is a separate reviewed UI action.
set -euo pipefail
source_dir=$(cd "$(dirname "$0")" && pwd)
id=io.github.loongsuite.pilot
: "${OMARCHY_PATH:?Run from the Omarchy session or pass its existing OMARCHY_PATH}"
export PATH="$OMARCHY_PATH/bin:$PATH"
omarchy-shell shell ping >/dev/null
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
python3 "$source_dir/tools/package.py" "$stage"
omarchy-plugin-validate "$stage"
destination="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/$id"
mkdir -p "$(dirname "$destination")"
if [[ -e "$destination" ]]; then
  backup="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/pilot-backups/$(date +%Y%m%d-%H%M%S)-$$"
  mkdir -p "$(dirname "$backup")"
  mv "$destination" "$backup"
  echo "Previous plugin: $backup"
fi
cp -R "$stage" "$destination"
omarchy-shell shell rescanPlugins
omarchy-plugin-enable "$id" --section right
echo 'Agent Activity installed. Open Setup to review Pilot; no collector settings changed.'

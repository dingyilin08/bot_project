#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/qq-rpg}"
SERVICE_NAME="${SERVICE_NAME:-qq-rpg.service}"
TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
    mapfile -t releases < <(find "$APP_ROOT/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)
    [[ ${#releases[@]} -ge 2 ]] || { echo "No previous release is available." >&2; exit 1; }
    TARGET="$APP_ROOT/releases/${releases[1]}"
elif [[ "$TARGET" != /* ]]; then
    TARGET="$APP_ROOT/releases/$TARGET"
fi

[[ -d "$TARGET" ]] || { echo "Release not found: $TARGET" >&2; exit 2; }
ln -sfn "$TARGET" "$APP_ROOT/current"
sudo systemctl restart "$SERVICE_NAME"
curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null
echo "Rolled back to: $(basename "$TARGET")"

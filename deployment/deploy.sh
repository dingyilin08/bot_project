#!/usr/bin/env bash
set -euo pipefail
umask 022

APP_ROOT="${APP_ROOT:-/opt/qq-rpg}"
SOURCE_DIR="${1:?Usage: deploy.sh SOURCE_DIRECTORY}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"
SERVICE_NAME="${SERVICE_NAME:-qq-rpg.service}"
VERSION="$(date -u +%Y%m%d%H%M%S)-${GITHUB_SHA:-manual}"
RELEASE_DIR="$APP_ROOT/releases/$VERSION"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_RELEASE=""

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "Source directory does not exist: $SOURCE_DIR" >&2
    exit 2
fi

mkdir -p "$APP_ROOT/releases" "$APP_ROOT/shared/logs"
if [[ -L "$CURRENT_LINK" ]]; then
    PREVIOUS_RELEASE="$(readlink -f "$CURRENT_LINK")"
fi

mkdir "$RELEASE_DIR"
rsync -a --delete \
    --exclude '.git/' \
    --exclude '.github/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '*.log' \
    "$SOURCE_DIR/" "$RELEASE_DIR/"
ln -sfn "$APP_ROOT/shared/logs/con_error.log" "$RELEASE_DIR/con_error.log"

python3 -m venv "$RELEASE_DIR/.venv"
"$RELEASE_DIR/.venv/bin/pip" install --disable-pip-version-check -r "$RELEASE_DIR/requirements.txt"
"$RELEASE_DIR/.venv/bin/python" -m compileall -q "$RELEASE_DIR"

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

if ! sudo systemctl restart "$SERVICE_NAME"; then
    echo "Service restart failed; restoring the previous release." >&2
    [[ -n "$PREVIOUS_RELEASE" ]] && ln -sfn "$PREVIOUS_RELEASE" "$CURRENT_LINK"
    sudo systemctl restart "$SERVICE_NAME" || true
    exit 1
fi

if ! curl --fail --silent --show-error --retry 10 --retry-delay 1 http://127.0.0.1:8000/health >/dev/null; then
    echo "Health check failed; restoring the previous release." >&2
    [[ -n "$PREVIOUS_RELEASE" ]] && ln -sfn "$PREVIOUS_RELEASE" "$CURRENT_LINK"
    sudo systemctl restart "$SERVICE_NAME" || true
    exit 1
fi

mapfile -t old_releases < <(find "$APP_ROOT/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r | tail -n +$((KEEP_RELEASES + 1)))
for release in "${old_releases[@]}"; do
    rm -rf -- "$APP_ROOT/releases/$release"
done

echo "Deployment succeeded: $VERSION"

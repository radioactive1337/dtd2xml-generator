#!/bin/sh
set -eu

CONFIG_DIR="/app/config"
APP_CONFIG="${CONFIG_DIR}/app.json"
APP_EXAMPLE="${CONFIG_DIR}/app.json.example"
DATA_DIR="/app/data"

check_not_directory() {
  target="$1"
  if [ -d "$target" ]; then
    echo "ERROR: ${target} is a directory, not a file."
    echo "Docker creates a folder when a bind-mounted file is missing on first start."
    exit 1
  fi
}

check_not_directory "$APP_CONFIG"

mkdir -p "$DATA_DIR"

if [ ! -f "$APP_CONFIG" ]; then
  if [ -f "$APP_EXAMPLE" ]; then
    echo "app.json not found, copying from example..."
    cp "$APP_EXAMPLE" "$APP_CONFIG"
  else
    echo "ERROR: app.json not found. Copy config/app.json.example to config/app.json"
    exit 1
  fi
fi

PORT="$(python -c 'from app.config import get_app_settings; print(get_app_settings().port)')"
HOST="$(python -c 'from app.config import get_app_settings; print(get_app_settings().host)')"

exec uvicorn app.main:app --host "$HOST" --port "$PORT"

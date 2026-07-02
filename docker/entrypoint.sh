#!/bin/sh
set -eu

CONFIG_DIR="/app/config"
CONFIG_FILE="${CONFIG_DIR}/connections.json"
LEGACY_FILE="/app/connections.json"

check_not_directory() {
  target="$1"
  if [ -d "$target" ]; then
    echo "ERROR: ${target} is a directory, not a file."
    echo "Docker creates a folder when a bind-mounted file is missing on first start."
    echo ""
    echo "Fix on Windows:"
    echo "  1. docker compose down"
    echo "  2. Remove-Item -Recurse -Force connections.json"
    echo "  3. copy config\\connections.json.example config\\connections.json"
    echo "  4. docker compose up --build"
    exit 1
  fi
}

check_not_directory "$LEGACY_FILE"
check_not_directory "$CONFIG_FILE"

if [ ! -f "$CONFIG_FILE" ] && [ ! -f "$LEGACY_FILE" ]; then
  if [ -f "${CONFIG_DIR}/connections.json.example" ]; then
    echo "connections.json not found, copying from example..."
    cp "${CONFIG_DIR}/connections.json.example" "$CONFIG_FILE"
    echo "Edit config/connections.json on the host and restart the container."
  else
    echo "ERROR: connections.json not found."
    echo "Copy config/connections.json.example to config/connections.json before starting Docker."
    exit 1
  fi
fi

PORT="$(python -c 'from app.config import get_app_settings; print(get_app_settings().port)')"
HOST="$(python -c 'from app.config import get_app_settings; print(get_app_settings().host)')"

exec uvicorn app.main:app --host "$HOST" --port "$PORT"

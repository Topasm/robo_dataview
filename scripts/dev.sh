#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-3000}"

cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

if [[ "${ROBOT_DATA_STUDIO_CLEAN_NEXT:-0}" == "1" ]]; then
  echo "Cleaning stale Next dev cache at apps/web/.next"
  rm -rf "$ROOT_DIR/apps/web/.next"
fi

require_port_free() {
  local host="$1"
  local port="$2"
  python3 - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.25)
    if sock.connect_ex((host, port)) == 0:
        raise SystemExit(1)
PY
}

cleanup() {
  jobs -pr | xargs -r kill
}
trap cleanup EXIT INT TERM

if ! require_port_free "$API_HOST" "$API_PORT"; then
  echo "API port ${API_HOST}:${API_PORT} is already in use." >&2
  exit 1
fi
if ! require_port_free "$WEB_HOST" "$WEB_PORT"; then
  echo "Web port ${WEB_HOST}:${WEB_PORT} is already in use." >&2
  exit 1
fi

echo "Starting Robot Data Studio API at http://${API_HOST}:${API_PORT}"
python3 -m uvicorn apps.api.main:app --reload --host "$API_HOST" --port "$API_PORT" &

echo "Starting Robot Data Studio web at http://${WEB_HOST}:${WEB_PORT}"
if command -v bun >/dev/null 2>&1; then
  NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://${API_HOST}:${API_PORT}/api}" \
    bash -c "cd apps/web && bun run dev -- --hostname '$WEB_HOST' --port '$WEB_PORT'" &
else
  NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://${API_HOST}:${API_PORT}/api}" \
    npm --workspace apps/web run dev -- --hostname "$WEB_HOST" --port "$WEB_PORT" &
fi

wait

#!/usr/bin/env bash
# Launch backend + frontend together. Ctrl+C stops both.
#
# Usage:
#   ./run.sh                 # full launch (installs deps on first run)
#   ./run.sh --skip-install  # fast restart, skip deps
#   BACKEND_PORT=8001 ./run.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
BACKEND_PORT="${BACKEND_PORT:-8000}"

SKIP_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --skip-install) SKIP_INSTALL=1 ;;
    -h|--help)
      sed -n '2,9p' "$0"
      exit 0
      ;;
  esac
done

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not on PATH" >&2; exit 1; }
}

section() { printf "\n==> %s\n" "$1"; }

require python3
require npm

# Resolve venv interpreter cross-platform
if [ -x "$VENV/bin/python" ]; then
  VENV_PY="$VENV/bin/python"
  VENV_PIP="$VENV/bin/pip"
elif [ -x "$VENV/Scripts/python.exe" ]; then
  VENV_PY="$VENV/Scripts/python.exe"
  VENV_PIP="$VENV/Scripts/pip.exe"
else
  section "Creating Python venv at backend/.venv"
  python3 -m venv "$VENV"
  if [ -x "$VENV/bin/python" ]; then
    VENV_PY="$VENV/bin/python"; VENV_PIP="$VENV/bin/pip"
  else
    VENV_PY="$VENV/Scripts/python.exe"; VENV_PIP="$VENV/Scripts/pip.exe"
  fi
fi

if [ "$SKIP_INSTALL" -eq 0 ]; then
  section "Installing backend deps (slow first time — torch ~750MB)"
  # Use `python -m pip` because pip cannot upgrade itself when invoked directly on Windows
  "$VENV_PY" -m pip install --upgrade pip >/dev/null
  "$VENV_PY" -m pip install -r "$BACKEND/requirements.txt"
fi

if [ "$SKIP_INSTALL" -eq 0 ] && [ ! -d "$FRONTEND/node_modules" ]; then
  section "Installing frontend deps"
  ( cd "$FRONTEND" && npm install )
fi

BACK_PID=""
FRONT_PID=""

kill_tree() {
  # Recursively kill a process and all its descendants. `npm run dev` and
  # `uvicorn --reload` both spawn children that survive a plain `kill $PID`.
  local pid="$1"
  [ -z "$pid" ] && return
  # collect descendants first (POSIX pgrep -P walks one level; loop deepens)
  local pids="$pid"
  local frontier="$pid"
  while [ -n "$frontier" ]; do
    local next=""
    for p in $frontier; do
      local kids
      kids=$(pgrep -P "$p" 2>/dev/null || true)
      [ -n "$kids" ] && next="$next $kids"
    done
    frontier="$next"
    [ -n "$next" ] && pids="$pids $next"
  done
  kill $pids 2>/dev/null || true
  sleep 0.5
  kill -9 $pids 2>/dev/null || true
}

cleanup() {
  echo ""
  echo "Stopping..."
  kill_tree "$BACK_PID"
  kill_tree "$FRONT_PID"
  wait 2>/dev/null || true
  echo "Stopped."
}
trap cleanup INT TERM EXIT

section "Starting backend on http://127.0.0.1:$BACKEND_PORT"
( cd "$ROOT" && "$VENV_PY" -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT" --reload ) &
BACK_PID=$!

section "Starting frontend on http://localhost:5173"
( cd "$FRONTEND" && npm run dev ) &
FRONT_PID=$!

echo ""
echo "Backend  PID $BACK_PID  http://127.0.0.1:$BACKEND_PORT/docs"
echo "Frontend PID $FRONT_PID  http://localhost:5173"
echo "Ctrl+C stops both."

# exit when either child dies
while kill -0 "$BACK_PID" 2>/dev/null && kill -0 "$FRONT_PID" 2>/dev/null; do
  sleep 1
done

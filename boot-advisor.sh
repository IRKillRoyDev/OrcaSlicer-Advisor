#!/bin/bash
# Started by OrcaSlicer Advisor.app. The app does not wait on this script.
# Usage: boot-advisor.sh PROJECT_DIR APPLET_PID
set -u

ROOT="${1:-}"
PARENT="${2:-}"
if [[ -z "$ROOT" || ! -x "$ROOT/venv/bin/uvicorn" ]]; then
  exit 1
fi

WORK="$ROOT/work"
LOG="$WORK/server.log"
APPLOG="$WORK/app.log"
PIDFILE="$WORK/server.pid"
mkdir -p "$WORK"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$1" >>"$APPLOG"
}

still_parent() {
  [[ -n "$PARENT" ]] && kill -0 "$PARENT" 2>/dev/null
}

log "boot parent=${PARENT:-none}"

if [[ -f "$PIDFILE" ]]; then
  old="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "${old:-}" ]]; then
    kill "$old" 2>/dev/null || true
  fi
fi

if [[ -x /usr/sbin/lsof ]]; then
  while read -r pid; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done < <(/usr/sbin/lsof -nP -t -iTCP:8777 -sTCP:LISTEN 2>/dev/null || true)
fi
sleep 0.2

if ! still_parent; then
  log "applet quit before start"
  exit 0
fi

cd "$ROOT"
"$ROOT/venv/bin/uvicorn" app:app --host 127.0.0.1 --port 8777 >>"$LOG" 2>&1 &
uv=$!
echo "$uv" >"$PIDFILE"
log "server pid $uv"

(
  while kill -0 "$PARENT" 2>/dev/null; do
    sleep 0.5
  done
  kill "$uv" 2>/dev/null || true
  log "applet gone, server stopped"
) &

for _ in $(seq 1 40); do
  still_parent || exit 0
  if /usr/bin/curl -sf -o /dev/null --max-time 0.4 "http://127.0.0.1:8777/"; then
    log "server ready"
    wait "$uv"
    exit 0
  fi
  sleep 0.25
done
log "server did not answer on port 8777"
kill "$uv" 2>/dev/null || true
exit 1

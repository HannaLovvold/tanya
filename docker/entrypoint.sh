#!/usr/bin/env bash
set -euo pipefail

# Tanya container entrypoint.
#   1. Render OpenClaw config + workspace files from env vars (idempotent).
#   2. Start the gateway in the FOREGROUND (systemd isn't available inside
#      containers, so `openclaw gateway start` doesn't actually bind a port;
#      we run the gateway as PID 1's child so it owns the main process).
#   3. Install OpenClaw crons on first boot (marker in the mounted volume).
#   4. Tail OpenClaw's file logs to stdout so `docker compose logs` is useful.

export REPO_ROOT="${REPO_ROOT:-/app/tanya}"
export TARGET_ROOT="${TARGET_ROOT:-/root/.openclaw}"
TARGET_SCRIPTS="$TARGET_ROOT/scripts"
CRON_MARKER="$TARGET_ROOT/.tanya-crons-installed"

log() { printf '[tanya] %s\n' "$*"; }

# Decide render mode: first boot (no state.json yet) = init, else configure.
if [[ -f "$TARGET_ROOT/workspace/data/state.json" ]]; then
  export MODE="${MODE:-configure}"
else
  export MODE="${MODE:-init}"
fi

# Gateway token must persist across restarts. Reuse the one already written
# to openclaw.json if .env didn't set it; generate if neither has one.
if [[ -z "${GATEWAY_TOKEN:-}" ]]; then
  if [[ -f "$TARGET_ROOT/openclaw.json" ]]; then
    GATEWAY_TOKEN="$(python3 -c '
import json
try:
    cfg = json.load(open("/root/.openclaw/openclaw.json"))
    print(cfg.get("gateway", {}).get("auth", {}).get("token", ""))
except Exception:
    pass
')"
  fi
  if [[ -z "${GATEWAY_TOKEN:-}" ]]; then
    GATEWAY_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
  fi
  export GATEWAY_TOKEN
fi

log "Rendering config (mode=$MODE)"
python3 "$REPO_ROOT/docker/render_runtime.py"

chmod 700 "$TARGET_ROOT" 2>/dev/null || true
chmod 700 "$TARGET_ROOT/workspace" 2>/dev/null || true
chmod 700 "$TARGET_ROOT/credentials" 2>/dev/null || true

# Detect the foreground gateway command. OpenClaw uses `gateway run` in recent
# versions; fall back to invoking the installed dist/index.js directly if the
# subcommand isn't recognised (older images or renamed verbs).
GATEWAY_CMD=()
if openclaw gateway --help 2>&1 | grep -qE '^[[:space:]]*run\b'; then
  GATEWAY_CMD=(openclaw gateway run)
elif openclaw --help 2>&1 | grep -qE '^[[:space:]]*serve\b'; then
  GATEWAY_CMD=(openclaw serve)
else
  OC_ENTRY="$(node -e 'try{console.log(require.resolve("openclaw/dist/index.js"))}catch(e){}')"
  if [[ -n "$OC_ENTRY" && -f "$OC_ENTRY" ]]; then
    GATEWAY_CMD=(node "$OC_ENTRY")
  else
    log "ERROR: could not determine a foreground gateway command."
    log "Run 'openclaw gateway --help' inside the container to find the right verb,"
    log "then update docker/entrypoint.sh accordingly."
    exit 1
  fi
fi

log "Starting gateway: ${GATEWAY_CMD[*]}"
"${GATEWAY_CMD[@]}" &
GATEWAY_PID=$!

# If the gateway dies, exit so docker's restart policy kicks in.
trap 'kill -TERM "$GATEWAY_PID" 2>/dev/null || true; wait "$GATEWAY_PID" 2>/dev/null || true; exit $?' TERM INT

# Wait for the gateway to accept connections before touching CLI commands.
READY=0
for _ in $(seq 1 60); do
  if openclaw gateway probe >/dev/null 2>&1; then
    READY=1
    break
  fi
  # If the gateway died during startup, don't keep probing.
  if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

if [[ "$READY" != "1" ]]; then
  log "ERROR: gateway did not become healthy. Recent logs:"
  for f in "$TARGET_ROOT/logs/"*.log /tmp/openclaw/openclaw-*.log; do
    [[ -f "$f" ]] || continue
    log "--- $f ---"
    tail -n 40 "$f" || true
  done
  # Surface the gateway process's own stderr via `wait`.
  wait "$GATEWAY_PID" 2>/dev/null || true
  exit 1
fi

log "Gateway is healthy."

if [[ ! -f "$CRON_MARKER" ]]; then
  log "Installing OpenClaw crons (first boot)"
  if TANYA_MAIN_MODEL="${MAIN_MODEL:-openai/gpt-5.4}" \
     TANYA_MINI_MODEL="${MINI_MODEL:-openai/gpt-5.4-mini}" \
     TANYA_ENABLE_WEB_SEARCH="${ENABLE_WEB:-0}" \
     "$TARGET_SCRIPTS/add_tanya_crons.sh"; then
    touch "$CRON_MARKER"
    log "Crons installed"
  else
    log "WARN: cron install failed; will retry on next boot"
  fi
fi

log "Tanya is live. Send your Telegram bot a message to get the pairing code."
log "Approve it with: docker compose exec tanya openclaw pairing approve telegram <CODE>"

# Stream OpenClaw's file logs to container stdout so `docker compose logs` is
# useful. Files don't exist at boot — tail -F retries until they appear.
mkdir -p "$TARGET_ROOT/logs" /tmp/openclaw
( tail -n 0 -F "$TARGET_ROOT/logs/"*.log /tmp/openclaw/openclaw-*.log 2>/dev/null ) &
TAIL_PID=$!

# The gateway is the container's main long-lived process. When it exits,
# we exit with the same status and Docker's restart policy handles recovery.
wait "$GATEWAY_PID"
STATUS=$?
kill "$TAIL_PID" 2>/dev/null || true
log "Gateway exited with status $STATUS."
exit "$STATUS"

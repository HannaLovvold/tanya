#!/usr/bin/env bash
set -euo pipefail

ELEVENLABS_API_KEY="${ELEVENLABS_API_KEY:-<ELEVENLABS_API_KEY>}"
ELEVENLABS_AGENT_ID="${ELEVENLABS_AGENT_ID:-<ELEVENLABS_AGENT_ID>}"
ELEVENLABS_PHONE_NUMBER_ID="${ELEVENLABS_PHONE_NUMBER_ID:-<ELEVENLABS_PHONE_NUMBER_ID>}"

TO_NUMBER="$1"
CONTEXT="${2:-}"
OPENING="${3:-}"

if [[ "$ELEVENLABS_API_KEY" == \<* || "$ELEVENLABS_AGENT_ID" == \<* || "$ELEVENLABS_PHONE_NUMBER_ID" == \<* ]]; then
  echo "Update /root/.openclaw/scripts/call_user.sh with your ElevenLabs API key, agent ID, and phone number ID before using calls." >&2
  exit 1
fi

curl -sS -X POST https://api.elevenlabs.io/v1/convai/twilio/outbound-call \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_id\": \"$ELEVENLABS_AGENT_ID\",
    \"agent_phone_number_id\": \"$ELEVENLABS_PHONE_NUMBER_ID\",
    \"to_number\": \"$TO_NUMBER\",
    \"conversation_initiation_client_data\": {
      \"dynamic_variables\": {
        \"current_context\": $(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
        \"opening_line_hint\": $(printf '%s' "$OPENING" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
      }
    }
  }"

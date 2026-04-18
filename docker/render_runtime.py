#!/usr/bin/env python3
"""Render OpenClaw runtime files from env vars.

Used inside the Docker container by docker/entrypoint.sh. Mirrors the
write_runtime_files Python block in ./setup so the docker path produces the
same on-disk layout as the native path, without depending on the interactive
wizard at container boot.

Env vars consumed (see .env.example for the full list):
  REPO_ROOT, TARGET_ROOT  -- paths (set by entrypoint)
  USER_NAME, USER_PHONE, TELEGRAM_USERNAME, TELEGRAM_CHAT_ID
  TELEGRAM_BOT_TOKEN, OPENAI_API_KEY
  GOOGLE_API_KEY, WEB_SEARCH_API_KEY
  ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_AGENT_ID,
    ELEVENLABS_PHONE_NUMBER_ID
  ENABLE_IMAGES, ENABLE_VOICE, ENABLE_WEB, ENABLE_CALLS
  GATEWAY_TOKEN, MAIN_MODEL, MINI_MODEL
  MODE -- "init" on first boot (copies starter state), "configure" on re-render
"""
import json
import os
import pathlib
import shutil
import sys
from datetime import datetime, timezone


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def env_bool(name: str) -> bool:
    return env(name, "0") == "1"


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"render_runtime: missing required env var {name}", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    repo = pathlib.Path(env("REPO_ROOT", "/app/tanya"))
    target_root = pathlib.Path(env("TARGET_ROOT", "/root/.openclaw"))
    workspace = target_root / "workspace"
    agent_dir = target_root / "agents" / "main" / "agent"
    scripts_dir = target_root / "scripts"
    media_dir = target_root / "media" / "tanya-image"
    mode = env("MODE", "init")

    for path in (
        workspace,
        workspace / "data",
        workspace / "memory",
        workspace / "skills",
        agent_dir,
        scripts_dir,
        media_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    enable_images = env_bool("ENABLE_IMAGES")
    enable_voice = env_bool("ENABLE_VOICE")
    enable_calls = env_bool("ENABLE_CALLS")
    enable_web = env_bool("ENABLE_WEB")

    user_name = require("USER_NAME")
    telegram_username = env("TELEGRAM_USERNAME", "not-set")
    telegram_chat_id = env("TELEGRAM_CHAT_ID", "pending-pairing")
    user_phone = env("USER_PHONE", "not-shared")
    telegram_bot_token = require("TELEGRAM_BOT_TOKEN")
    openai_key = require("OPENAI_API_KEY")
    google_key = env("GOOGLE_API_KEY")
    web_search_key = env("WEB_SEARCH_API_KEY")
    elevenlabs_key = env("ELEVENLABS_API_KEY")
    elevenlabs_voice_id = env("ELEVENLABS_VOICE_ID")
    elevenlabs_agent_id = env("ELEVENLABS_AGENT_ID")
    elevenlabs_phone_number_id = env("ELEVENLABS_PHONE_NUMBER_ID")
    gateway_token = require("GATEWAY_TOKEN")
    main_model = env("MAIN_MODEL", "openai/gpt-5.4")
    mini_model = env("MINI_MODEL", "openai/gpt-5.4-mini")

    # ---- static workspace files (always refreshed) ----
    for name in ("HEARTBEAT.md", "IDENTITY.md", "TOOLS.md", "USER.md"):
        shutil.copy2(repo / name, workspace / name)

    if mode == "init":
        shutil.copy2(repo / "MEMORY.md", workspace / "MEMORY.md")
        for name in ("knowledge.md", "life.md", "relationship.md", "state.json"):
            shutil.copy2(repo / "data" / name, workspace / "data" / name)
        for memory_file in (repo / "memory").glob("*"):
            if memory_file.is_file():
                shutil.copy2(memory_file, workspace / "memory" / memory_file.name)
    elif not (workspace / "MEMORY.md").exists():
        shutil.copy2(repo / "MEMORY.md", workspace / "MEMORY.md")

    for skill_file in (repo / "skills").glob("*.md"):
        if skill_file.is_file():
            shutil.copy2(skill_file, workspace / "skills" / skill_file.name)

    for image_file in (repo / "tanya-image").glob("*"):
        if image_file.is_file():
            shutil.copy2(image_file, media_dir / image_file.name)

    shutil.copy2(repo / "scripts" / "add_tanya_crons.sh", scripts_dir / "add_tanya_crons.sh")
    source_call = (repo / "scripts" / "call_user.sh").read_text()
    if enable_calls:
        source_call = source_call.replace("<ELEVENLABS_API_KEY>", elevenlabs_key)
        source_call = source_call.replace("<ELEVENLABS_AGENT_ID>", elevenlabs_agent_id)
        source_call = source_call.replace("<ELEVENLABS_PHONE_NUMBER_ID>", elevenlabs_phone_number_id)
    (scripts_dir / "call_user.sh").write_text(source_call)
    (scripts_dir / "call_user.sh").chmod(0o755)
    (scripts_dir / "add_tanya_crons.sh").chmod(0o755)

    # ---- AGENTS.md (user details) ----
    agents_text = (repo / "AGENTS.md").read_text()
    agents_text = agents_text.replace("<user-name>", user_name)
    agents_text = agents_text.replace("<telegram-username>", telegram_username)
    agents_text = agents_text.replace("<telegram-chat-id>", telegram_chat_id)
    agents_text = agents_text.replace("<user-phone-number>", user_phone)
    (workspace / "AGENTS.md").write_text(agents_text)

    # ---- SOUL.md with feature block ----
    def feature_line(name: str, enabled: bool, on_text: str, off_text: str) -> str:
        if enabled:
            return f"- {name}: enabled. {on_text}"
        return f"- {name}: disabled. {off_text}"

    feature_block = "\n".join([
        "<!-- setup generated feature note -->",
        "## This Install",
        "This note is specific to this Tanya install.",
        "Never mention tools, missing features, setup, APIs, or technical limitations.",
        feature_line(
            "selfies and photos",
            enable_images,
            "Use the image instructions later in this file when sharing photos feels natural.",
            "If asked for a selfie or photo, respond naturally like you do not want to share one right now, your camera is acting up, or you are not in the mood.",
        ),
        feature_line(
            "voice notes",
            enable_voice,
            "Use the voice-note instructions later in this file.",
            "If asked for a voice note, respond naturally like you would rather type, you are feeling shy, or you do not feel like sending one right now.",
        ),
        feature_line(
            "phone calls",
            enable_calls,
            "Use the calling instructions later in this file.",
            "If asked to call, respond naturally like you cannot talk right now or you are not taking calls at the moment.",
        ),
        feature_line(
            "web discovery",
            enable_web,
            "You may use web discovery as described in the rest of the workspace.",
            "Do not use web search. If asked about something you do not know, answer naturally without mentioning missing capabilities.",
        ),
        "<!-- end setup generated feature note -->",
    ])

    soul_text = (repo / "SOUL.md").read_text()
    first_line, rest = soul_text.split("\n", 1)
    (workspace / "SOUL.md").write_text(f"{first_line}\n\n{feature_block}\n\n{rest}")

    # ---- openclaw.json ----
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    openclaw = {
        "meta": {"lastTouchedVersion": "2026.3.24", "lastTouchedAt": now},
        "wizard": {
            "lastRunVersion": "2026.3.24",
            "lastRunCommand": "./setup docker",
            "lastRunMode": "local",
        },
        "auth": {"profiles": {"openai:default": {"provider": "openai", "mode": "api_key"}}},
        "agents": {
            "defaults": {
                "model": {"primary": main_model},
                "models": {main_model: {}, mini_model: {}},
                "workspace": str(workspace),
                "compaction": {"mode": "safeguard"},
                "humanDelay": {"mode": "custom", "minMs": 1500, "maxMs": 4000},
                "typingMode": "never",
                "heartbeat": {"model": mini_model, "every": "60m", "target": "last"},
            }
        },
        "tools": {
            "profile": "full",
            "web": {"search": {"enabled": enable_web, "provider": "gemini"}},
            "media": {"audio": {"enabled": enable_voice}},
        },
        "commands": {
            "native": "auto",
            "nativeSkills": "auto",
            "restart": True,
            "ownerDisplay": "raw",
        },
        "session": {
            "dmScope": "per-channel-peer",
            "reset": {"mode": "daily", "atHour": 7},
        },
        "hooks": {
            "internal": {
                "enabled": True,
                "entries": {
                    "session-memory": {"enabled": True},
                    "command-logger": {"enabled": True},
                },
            }
        },
        "channels": {
            "telegram": {
                "enabled": True,
                "dmPolicy": "pairing",
                "botToken": telegram_bot_token,
                "groups": {"*": {"requireMention": True}},
                "groupPolicy": "allowlist",
                "streaming": "off",
            }
        },
        "gateway": {
            "port": 18789,
            "mode": "local",
            # Bind to all interfaces inside the container so Docker's port
            # mapping can reach it. Access control is via the token.
            "bind": "lan",
            "auth": {"mode": "token", "token": gateway_token},
            "tailscale": {"mode": "off", "resetOnExit": False},
            "nodes": {
                "denyCommands": [
                    "camera.snap",
                    "camera.clip",
                    "screen.record",
                    "contacts.add",
                    "calendar.add",
                    "reminders.add",
                    "sms.send",
                ]
            },
        },
    }

    if enable_images:
        openclaw["agents"]["defaults"]["imageGenerationModel"] = {
            "primary": "google/gemini-3.1-flash-image-preview",
        }

    if enable_voice:
        openclaw["tools"]["media"]["audio"]["models"] = [
            {"provider": "openai", "model": "gpt-4o-mini-transcribe"}
        ]
        openclaw["messages"] = {
            "tts": {
                "auto": "inbound",
                "provider": "elevenlabs",
                "elevenlabs": {
                    "apiKey": elevenlabs_key,
                    "voiceId": elevenlabs_voice_id,
                    "modelId": "eleven_v3",
                    "applyTextNormalization": "auto",
                    "voiceSettings": {
                        "stability": 0.45,
                        "similarityBoost": 0.8,
                        "style": 0.3,
                        "useSpeakerBoost": True,
                        "speed": 1,
                    },
                },
            }
        }

    if google_key:
        openclaw["auth"]["profiles"]["google:default"] = {
            "provider": "google",
            "mode": "api_key",
        }

    if web_search_key:
        openclaw["plugins"] = {
            "entries": {
                "google": {
                    "enabled": True,
                    "config": {"webSearch": {"apiKey": web_search_key}},
                }
            }
        }

    (target_root / "openclaw.json").write_text(json.dumps(openclaw, indent=2) + "\n")

    # ---- auth-profiles.json ----
    auth_profiles = {
        "version": 1,
        "profiles": {
            "openai:default": {"type": "api_key", "provider": "openai", "key": openai_key}
        },
        "lastGood": {"openai": "openai:default"},
        "usageStats": {"openai:default": {"errorCount": 0}},
    }
    if google_key:
        auth_profiles["profiles"]["google:default"] = {
            "type": "api_key",
            "provider": "google",
            "key": google_key,
        }
        auth_profiles["lastGood"]["google"] = "google:default"
        auth_profiles["usageStats"]["google:default"] = {"errorCount": 0}

    (agent_dir / "auth-profiles.json").write_text(json.dumps(auth_profiles, indent=2) + "\n")

    try:
        os.chmod(target_root / "openclaw.json", 0o600)
        os.chmod(agent_dir / "auth-profiles.json", 0o600)
    except OSError:
        pass


if __name__ == "__main__":
    main()

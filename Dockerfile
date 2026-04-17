# syntax=docker/dockerfile:1.6
FROM node:22-bookworm-slim

ARG OPENCLAW_VERSION=2026.3.24
ENV OPENCLAW_VERSION=${OPENCLAW_VERSION} \
    DEBIAN_FRONTEND=noninteractive \
    NODE_ENV=production \
    HOME=/root

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl python3 tini \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g --omit=dev openclaw@${OPENCLAW_VERSION} \
 && npm cache clean --force

# Stage the repo's source-of-truth files at /app/tanya. The entrypoint copies
# from here into /root/.openclaw/workspace on first boot (or on explicit
# re-render), leaving the workspace bind-mount free to hold live state.
WORKDIR /app/tanya
COPY SOUL.md USER.md HEARTBEAT.md AGENTS.md MEMORY.md IDENTITY.md TOOLS.md ./
COPY data ./data
COPY memory ./memory
COPY skills ./skills
COPY scripts ./scripts
COPY templates ./templates
COPY tanya-image ./tanya-image
COPY docker/entrypoint.sh /usr/local/bin/tanya-entrypoint
COPY docker/render_runtime.py /app/tanya/docker/render_runtime.py

RUN chmod +x /usr/local/bin/tanya-entrypoint \
             /app/tanya/scripts/add_tanya_crons.sh \
             /app/tanya/scripts/call_user.sh

EXPOSE 18789

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/tanya-entrypoint"]

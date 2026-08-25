#!/bin/sh
# Container entrypoint.
#
# Two modes, because this image serves two different things:
#
#   APP_MODE=web  -> the full dashboard (all six sections, including the agent
#                    pipeline) bound to 0.0.0.0 so a host can route to it.
#   anything else -> the interactive CLI, which is what upstream's image did and
#                    what docker-compose still expects.
#
# Container hosts (Hugging Face Spaces, Render, Fly, Railway) run a process that
# stays up and may hold a request open for minutes, so the agent pipeline works
# here — unlike a serverless function, which is killed after seconds.
set -e

if [ "$APP_MODE" = "web" ]; then
    # HF Spaces expects 7860; Render/Fly/Railway inject $PORT.
    export WEBUI_HOST="${WEBUI_HOST:-0.0.0.0}"
    export WEBUI_PORT="${WEBUI_PORT:-${PORT:-7860}}"
    export WEBUI_OPEN=0          # no browser to open inside a container
    echo "Starting TradingAgents dashboard on ${WEBUI_HOST}:${WEBUI_PORT}"
    exec python -m webui
fi

exec tradingagents "$@"

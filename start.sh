#!/usr/bin/env bash
# Start GramVaani services locally
# Usage: ./start.sh [--stop] [--fresh]

set -euo pipefail

PIDS_FILE=".running.pids"
LOG_DIR="logs"
LIVEKIT_CONTAINER="gramvaani-livekit"
LIVEKIT_DEV_KEY="devkey"
LIVEKIT_DEV_SECRET="secret"

stop_services() {
    echo "Stopping services..."
    if [[ -f "$PIDS_FILE" ]]; then
        while IFS= read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                echo "  Stopped PID $pid"
            fi
        done < "$PIDS_FILE"
        rm -f "$PIDS_FILE"
    fi
    if docker rm -f "$LIVEKIT_CONTAINER" 2>/dev/null; then
        echo "  Stopped LiveKit server container"
    fi
    echo "Done."
}

if [[ "${1:-}" == "--stop" ]]; then
    stop_services
    exit 0
fi

FRESH=false
if [[ "${1:-}" == "--fresh" ]]; then
    FRESH=true
fi

# Stop any previously started services first
[[ -f "$PIDS_FILE" ]] && stop_services

mkdir -p "$LOG_DIR"
: > "$PIDS_FILE"

# --fresh: drop and recreate all tables before starting
if [[ "$FRESH" == "true" ]]; then
    echo "Resetting database..."
    PYTHONPATH=src uv run python -c "import asyncio; from app.database import reset_db; asyncio.run(reset_db())"
    echo "Database reset complete."
fi

# 1. PostgreSQL — check it's running (expected to be managed separately)
if ! pg_isready -q -h localhost -p 5432; then
    echo "WARNING: PostgreSQL is not ready on localhost:5432."
    echo "  Start it with: brew services start postgresql@15"
    echo "  Or use Docker: docker-compose up -d postgres"
fi

# 2. LiveKit Server (self-hosted via Docker/Colima)
if docker inspect "$LIVEKIT_CONTAINER" &>/dev/null; then
    echo "LiveKit server already running."
else
    echo "Starting LiveKit server on ws://localhost:7880 ..."
    docker run -d --name "$LIVEKIT_CONTAINER" \
        -p 7880:7880 -p 7881:7881 -p 7882:7882/udp \
        -e "LIVEKIT_KEYS=${LIVEKIT_DEV_KEY}: ${LIVEKIT_DEV_SECRET}" \
        livekit/livekit-server \
        --dev --node-ip 127.0.0.1 \
        > /dev/null
fi

# Set LiveKit env vars for agent worker (use .env values if set, else dev defaults)
export LIVEKIT_URL="${LIVEKIT_URL:-ws://localhost:7880}"
export LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-$LIVEKIT_DEV_KEY}"
export LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-$LIVEKIT_DEV_SECRET}"

# 3. Backend (FastAPI — dashboard + webhooks)
echo "Starting backend on http://localhost:8000 ..."
PYTHONPATH=src uv run uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --reload \
    > "$LOG_DIR/backend.log" 2>&1 &
echo $! >> "$PIDS_FILE"

# 4. LiveKit Agent Worker (voice pipeline)
echo "Starting LiveKit agent worker ..."
PYTHONPATH=src uv run python -m app.livekit_agent dev \
    > "$LOG_DIR/livekit-agent.log" 2>&1 &
echo $! >> "$PIDS_FILE"

# 5. Dashboard (Next.js)
echo "Starting dashboard on http://localhost:3000 ..."
cd frontend && npm run dev \
    > "../$LOG_DIR/dashboard.log" 2>&1 &
echo $! >> "../$PIDS_FILE"
cd ..

echo ""
echo "Services started:"
echo "  LiveKit:   ws://localhost:7880 (Docker)"
echo "  Backend:   http://localhost:8000"
echo "  Agent:     LiveKit worker (voice pipeline)"
echo "  Dashboard: http://localhost:3000"
echo ""
echo "Logs: $LOG_DIR/"
echo "Stop:  ./start.sh --stop"
echo "Fresh: ./start.sh --fresh  (resets DB — all users deleted)"

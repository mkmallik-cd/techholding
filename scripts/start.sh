#!/usr/bin/env bash
# scripts/start.sh — Boot the full patient-dataset-generation + Langfuse stack.
#
# What this script does:
#   1.  Create the shared Docker network (idempotent)
#   2.  Start the Langfuse stack (docker-compose.langfuse.yml)
#   3.  Wait for the Langfuse Postgres to be healthy
#   4.  Start the main stack (docker-compose.yml)
#   5.  Wait for the main Postgres to be healthy
#   6.  Run Alembic migrations
#   7.  Print service URLs
#
# Usage:
#   ./scripts/start.sh          # start everything detached
#   ./scripts/start.sh --fg     # start everything, then follow logs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

NETWORK_NAME="patient_gen_network"
FOREGROUND=false
[[ "${1:-}" == "--fg" ]] && FOREGROUND=true

# ── helpers ────────────────────────────────────────────────────────────────────
log()  { printf '\e[34m[start.sh]\e[0m %s\n' "$*"; }
ok()   { printf '\e[32m[start.sh] ✓\e[0m %s\n' "$*"; }
fail() { printf '\e[31m[start.sh] ✗\e[0m %s\n' "$*" >&2; exit 1; }

wait_healthy() {
  local compose_file="$1"
  local service="$2"
  local max_wait=90
  local waited=0
  log "Waiting for $service to be healthy..."
  until docker compose -f "$compose_file" exec -T "$service" \
        sh -c 'pg_isready -U "${POSTGRES_USER:-postgres}" -q' 2>/dev/null; do
    (( waited >= max_wait )) && fail "$service did not become healthy within ${max_wait}s."
    sleep 3
    (( waited += 3 ))
  done
  ok "$service is healthy."
}

# ── 1. shared network ──────────────────────────────────────────────────────────
log "Creating shared Docker network '$NETWORK_NAME' (skipped if exists)..."
docker network create "$NETWORK_NAME" 2>/dev/null \
  && ok "Network '$NETWORK_NAME' created." \
  || ok "Network '$NETWORK_NAME' already exists."

# ── 2. Langfuse stack ──────────────────────────────────────────────────────────
log "Starting Langfuse stack..."
docker compose -f docker-compose.langfuse.yml up -d
ok "Langfuse stack started."

# ── 3. wait for Langfuse postgres ─────────────────────────────────────────────
wait_healthy "docker-compose.langfuse.yml" "postgres-langfuse"

# ── 4. main stack ─────────────────────────────────────────────────────────────
log "Starting main stack..."
docker compose up --build -d
ok "Main stack started."

# ── 5. wait for main postgres ─────────────────────────────────────────────────
wait_healthy "docker-compose.yml" "postgres"

# ── 6. run alembic migrations ─────────────────────────────────────────────────
log "Running Alembic migrations..."
docker compose exec -T api alembic upgrade head
ok "Migrations applied."

# ── 7. print URLs ──────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Stack is up!"
echo ""
echo "  API          →  http://localhost:8081"
echo "  RabbitMQ UI  →  http://localhost:15672  (guest/guest)"
echo "  Langfuse UI  →  http://localhost:3000"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  To enable LLM tracing, add these to your .env:"
echo "    LANGFUSE_ENABLED=true"
echo "    LANGFUSE_PUBLIC_KEY=<from Langfuse UI → Settings → API Keys>"
echo "    LANGFUSE_SECRET_KEY=<from Langfuse UI → Settings → API Keys>"
echo "  Then restart: docker compose restart api worker worker-step2 worker-step3 worker-step4 worker-step5 worker-step6 worker-step7"
echo ""

if [[ "$FOREGROUND" == true ]]; then
  log "Following logs (Ctrl+C to stop)..."
  docker compose logs -f
fi

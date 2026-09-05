#!/usr/bin/env bash
# =============================================================================
#  MedAudit — Full Stack Startup Script
#  Starts:  LLM Microservice (port 8001)
#           Backend API       (port 8000)
#           Frontend Dev      (port 3000)
#
#  Usage:
#    ./start.sh            — start all services
#    ./start.sh --stop     — stop all services
#    ./start.sh --logs     — tail all logs live
#    ./start.sh --status   — check which services are running
# =============================================================================

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR"
LLM_DIR="$(dirname "$SCRIPT_DIR")/medaudit-LLM"
FRONTEND_DIR="$SCRIPT_DIR/medaudit-frontend"
LOG_DIR="$SCRIPT_DIR/logs"
PID_DIR="$SCRIPT_DIR/.pids"

# ── Log files ─────────────────────────────────────────────────────────────────
LLM_LOG="$LOG_DIR/llm.log"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# ── PID files ─────────────────────────────────────────────────────────────────
LLM_PID="$PID_DIR/llm.pid"
BACKEND_PID="$PID_DIR/backend.pid"
FRONTEND_PID="$PID_DIR/frontend.pid"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo -e "${CYAN}[$(date '+%H:%M:%S')]${RESET} $*"; }
ok()   { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✔${RESET} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠${RESET} $*"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✘${RESET} $*"; }

banner() {
  echo -e "${BOLD}"
  echo "  ╔══════════════════════════════════════════╗"
  echo "  ║       MedAudit — Full Stack Startup       ║"
  echo "  ║  LLM :8001 | Backend :8000 | UI :3000    ║"
  echo "  ╚══════════════════════════════════════════╝"
  echo -e "${RESET}"
}

# Create directories
mkdir -p "$LOG_DIR" "$PID_DIR"

# Load .env from backend root
load_env() {
  ENV_FILE="$BACKEND_DIR/.env"
  if [[ -f "$ENV_FILE" ]]; then
    log "Loading credentials from .env"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  else
    warn ".env not found at $ENV_FILE — services may fail authentication"
  fi
}

# Check if a process is alive by PID file
is_running() {
  local pidfile="$1"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

# Wait until an HTTP endpoint responds (or timeout)
wait_for_port() {
  local name="$1"
  local url="$2"
  local timeout="${3:-30}"
  local elapsed=0
  printf "  Waiting for %s" "$name"
  while ! curl -sf "$url" > /dev/null 2>&1; do
    sleep 1
    elapsed=$((elapsed + 1))
    printf "."
    if [[ $elapsed -ge $timeout ]]; then
      echo ""
      err "$name did not become ready within ${timeout}s — check ${LOG_DIR}/"
      return 1
    fi
  done
  echo ""
  ok "$name is ready ($url)"
}

# ── STOP ──────────────────────────────────────────────────────────────────────
stop_services() {
  log "Stopping all MedAudit services..."
  for name in llm backend frontend; do
    pidfile="$PID_DIR/${name}.pid"
    if is_running "$pidfile"; then
      local pid
      pid=$(cat "$pidfile")
      kill "$pid" 2>/dev/null && ok "Stopped $name (pid $pid)" || warn "Could not stop $name"
      rm -f "$pidfile"
    else
      warn "$name was not running"
    fi
  done
  # Kill any stray processes on our ports
  for port in 8000 8001 3000; do
    fuser -k "${port}/tcp" 2>/dev/null || true
  done
  ok "All services stopped."
}

# ── STATUS ────────────────────────────────────────────────────────────────────
check_status() {
  echo ""
  echo -e "${BOLD}  MedAudit Service Status${RESET}"
  echo "  ─────────────────────────────────────"
  for item in "llm:8001:LLM Microservice" "backend:8000:Backend API" "frontend:3000:Frontend Dev"; do
    IFS=: read -r name port label <<< "$item"
    pidfile="$PID_DIR/${name}.pid"
    if is_running "$pidfile"; then
      pid=$(cat "$pidfile")
      echo -e "  ${GREEN}● RUNNING${RESET}  $label  (pid $pid, port $port)"
    else
      echo -e "  ${RED}○ STOPPED${RESET}  $label  (port $port)"
    fi
  done
  echo ""
}

# ── LOGS ──────────────────────────────────────────────────────────────────────
tail_logs() {
  log "Tailing all service logs (Ctrl+C to stop)..."
  echo ""
  tail -f \
    --label "[ LLM     ] " "$LLM_LOG" \
    --label "[ BACKEND ] " "$BACKEND_LOG" \
    --label "[ FRONTEND] " "$FRONTEND_LOG" 2>/dev/null || \
  tail -f "$LLM_LOG" "$BACKEND_LOG" "$FRONTEND_LOG"
}

# ── START ─────────────────────────────────────────────────────────────────────
start_services() {
  banner
  load_env

  # ── 1. LLM Microservice ──────────────────────────────────────────────────
  log "Starting LLM Microservice..."

  if ! [[ -d "$LLM_DIR" ]]; then
    err "medaudit-LLM not found at $LLM_DIR"
    err "Clone it: git clone https://github.com/sohail-kustagi/medaudit-LLM.git $(dirname "$SCRIPT_DIR")/medaudit-LLM"
    exit 1
  fi

  if ! [[ -d "$LLM_DIR/.venv" ]]; then
    log "Creating LLM virtualenv..."
    python3 -m venv "$LLM_DIR/.venv"
    "$LLM_DIR/.venv/bin/pip" install -q -r "$LLM_DIR/requirements.txt"
  fi

  {
    echo "════════════════════════════════════"
    echo " LLM Microservice — $(date)"
    echo "════════════════════════════════════"
  } > "$LLM_LOG"

  (
    cd "$LLM_DIR"
    # shellcheck disable=SC2086
    "$LLM_DIR/.venv/bin/uvicorn" main:app \
      --host 0.0.0.0 \
      --port 8001 \
      --log-level info \
      >> "$LLM_LOG" 2>&1
  ) &
  echo $! > "$LLM_PID"
  ok "LLM process started (pid $(cat "$LLM_PID"))"

  # ── 2. Backend API ───────────────────────────────────────────────────────
  log "Starting Backend API..."

  if ! [[ -d "$BACKEND_DIR/.venv" ]]; then
    log "Creating Backend virtualenv..."
    python3 -m venv "$BACKEND_DIR/.venv"
    "$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"
  fi

  {
    echo "════════════════════════════════════"
    echo " Backend API — $(date)"
    echo "════════════════════════════════════"
  } > "$BACKEND_LOG"

  (
    cd "$BACKEND_DIR"
    "$BACKEND_DIR/.venv/bin/uvicorn" backend.app.main:app \
      --host 0.0.0.0 \
      --port 8000 \
      --log-level info \
      >> "$BACKEND_LOG" 2>&1
  ) &
  echo $! > "$BACKEND_PID"
  ok "Backend process started (pid $(cat "$BACKEND_PID"))"

  # ── 3. Frontend Dev Server ───────────────────────────────────────────────
  log "Starting Frontend Dev Server..."

  if ! [[ -d "$FRONTEND_DIR/node_modules" ]]; then
    log "Installing frontend dependencies (npm install)..."
    npm --prefix "$FRONTEND_DIR" install --silent
  fi

  {
    echo "════════════════════════════════════"
    echo " Frontend Dev — $(date)"
    echo "════════════════════════════════════"
  } > "$FRONTEND_LOG"

  (
    cd "$FRONTEND_DIR"
    npm run dev -- --port 3000 \
      >> "$FRONTEND_LOG" 2>&1
  ) &
  echo $! > "$FRONTEND_PID"
  ok "Frontend process started (pid $(cat "$FRONTEND_PID"))"

  # ── Health checks ────────────────────────────────────────────────────────
  echo ""
  log "Waiting for all services to be ready..."
  wait_for_port "LLM Microservice"   "http://localhost:8001/health" 60
  wait_for_port "Backend API"        "http://localhost:8000/health" 30
  wait_for_port "Frontend Dev"       "http://localhost:3000"        30

  # ── Summary ──────────────────────────────────────────────────────────────
  echo ""
  echo -e "${BOLD}${GREEN}  ✔ All services are UP${RESET}"
  echo ""
  echo -e "  ${CYAN}LLM Microservice${RESET}  →  http://localhost:8001"
  echo -e "  ${CYAN}LLM API Docs${RESET}      →  http://localhost:8001/docs"
  echo -e "  ${CYAN}Backend API${RESET}       →  http://localhost:8000"
  echo -e "  ${CYAN}Backend API Docs${RESET}  →  http://localhost:8000/api/v1/openapi.json"
  echo -e "  ${CYAN}Frontend UI${RESET}       →  http://localhost:3000"
  echo ""
  echo -e "  Logs are written to ${YELLOW}$LOG_DIR/${RESET}"
  echo -e "  Run ${YELLOW}./start.sh --logs${RESET}   to tail all logs live"
  echo -e "  Run ${YELLOW}./start.sh --stop${RESET}   to stop all services"
  echo ""

  # Trap Ctrl+C to clean up
  trap 'echo ""; log "Shutting down..."; stop_services; exit 0' INT TERM

  # Keep script alive so logs can be followed
  log "Press Ctrl+C to stop all services"
  wait
}

# ── Entry Point ───────────────────────────────────────────────────────────────
case "${1:-}" in
  --stop)   stop_services  ;;
  --logs)   tail_logs      ;;
  --status) check_status   ;;
  --help|-h)
    echo "Usage: $0 [--stop | --logs | --status | --help]"
    echo ""
    echo "  (no args)   Start all services (LLM, Backend, Frontend)"
    echo "  --stop      Stop all running services"
    echo "  --logs      Tail all service logs live"
    echo "  --status    Check which services are currently running"
    ;;
  *)
    start_services
    ;;
esac

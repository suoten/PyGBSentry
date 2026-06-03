#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

check_prereqs() {
    local missing=()
    for cmd in docker; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    if ! docker compose version &>/dev/null && ! command -v docker-compose &>/dev/null; then
        missing+=("docker-compose")
    fi
    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing prerequisites: ${missing[*]}"
    fi
}

check_ports() {
    local ports=(80 8000 5060 5432 6379 8880)
    local in_use=()
    for port in "${ports[@]}"; do
        if ss -tlnp 2>/dev/null | grep -q ":${port} " || \
           netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
            in_use+=("$port")
        fi
    done
    if [[ ${#in_use[@]} -gt 0 ]]; then
        warn "Ports in use: ${in_use[*]}. Some services may fail to start."
    fi
}

do_healthcheck() {
    local max_attempts=30
    local attempt=1
    while [[ $attempt -le $max_attempts ]]; do
        if curl -sf http://localhost:8000/api/v1/health/ &>/dev/null; then
            info "Backend is healthy (attempt $attempt/$max_attempts)"
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    warn "Backend health check failed after $max_attempts attempts"
    return 1
}

show_admin_password() {
    local compose_cmd
    if docker compose version &>/dev/null; then
        compose_cmd="docker compose"
    else
        compose_cmd="docker-compose"
    fi
    echo ""
    info "Admin password (first run only):"
    $compose_cmd -f "$PROJECT_DIR/docker-compose.yml" logs backend 2>/dev/null | grep "Auto-generated admin password" | tail -1 || true
}

case "${1:-}" in
    start)
        check_prereqs
        check_ports
        cd "$PROJECT_DIR"
        if docker compose version &>/dev/null; then
            docker compose up -d --build
        else
            docker-compose up -d --build
        fi
        do_healthcheck
        show_admin_password
        ;;
    stop)
        cd "$PROJECT_DIR"
        if docker compose version &>/dev/null; then
            docker compose down
        else
            docker-compose down
        fi
        info "Services stopped"
        ;;
    restart)
        cd "$PROJECT_DIR"
        if docker compose version &>/dev/null; then
            docker compose restart
        else
            docker-compose restart
        fi
        do_healthcheck
        ;;
    status)
        cd "$PROJECT_DIR"
        if docker compose version &>/dev/null; then
            docker compose ps
        else
            docker-compose ps
        fi
        curl -sf http://localhost:8000/api/v1/health/ 2>/dev/null && echo "" || warn "Backend not responding"
        ;;
    logs)
        cd "$PROJECT_DIR"
        if docker compose version &>/dev/null; then
            docker compose logs -f "${2:-}"
        else
            docker-compose logs -f "${2:-}"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs} [service]"
        echo ""
        echo "Commands:"
        echo "  start    Build and start all services"
        echo "  stop     Stop all services"
        echo "  restart  Restart all services"
        echo "  status   Show service status"
        echo "  logs     Follow logs (optional: service name)"
        exit 1
        ;;
esac

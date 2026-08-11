#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()  { echo -e "${CYAN}[STEP]${NC} $*"; }

# ---------------------------------------------------------------------------
# 检测 Docker / docker-compose
# ---------------------------------------------------------------------------
get_compose_cmd() {
    if docker compose version &>/dev/null; then
        echo "docker compose"
    elif command -v docker-compose &>/dev/null; then
        echo "docker-compose"
    else
        echo ""
    }
}

check_prereqs() {
    local missing=()
    for cmd in docker; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    if [[ -z "$(get_compose_cmd)" ]]; then
        missing+=("docker-compose")
    fi
    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing prerequisites: ${missing[*]}. Please install Docker first: https://docs.docker.com/get-docker/"
    fi
}

# ---------------------------------------------------------------------------
# 端口检查
# ---------------------------------------------------------------------------
check_ports() {
    local ports=(80 8000 5060 8880 1935 554)
    local in_use=()
    for port in "${ports[@]}"; do
        if ss -tlnp 2>/dev/null | grep -q ":${port} " || \
           netstat -tlnp 2>/dev/null | grep -q ":${port} " 2>/dev/null; then
            in_use+=("$port")
        fi
    done
    if [[ ${#in_use[@]} -gt 0 ]]; then
        warn "Ports in use: ${in_use[*]}. Some services may fail to start."
        warn "You can change ports in docker-compose.yml or stop the conflicting services."
    fi
}

# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------
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
    compose_cmd="$(get_compose_cmd)"
    echo ""
    info "Admin password (first run only):"
    $compose_cmd -f "$PROJECT_DIR/docker-compose.yml" logs backend 2>/dev/null | grep "Auto-generated admin password" | tail -1 || true
}

# ---------------------------------------------------------------------------
# init: 自动生成 .env 并启动
# ---------------------------------------------------------------------------
do_init() {
    step "1/3 生成环境配置 (.env)..."
    if [[ -f "$PROJECT_DIR/backend/.env" ]]; then
        warn "backend/.env already exists. Use --force to overwrite."
        read -r -p "Overwrite? [y/N] " resp
        if [[ "$resp" != "y" && "$resp" != "Y" ]]; then
            info "Keeping existing .env file."
        else
            python3 "$PROJECT_DIR/tools/generate_env.py" --non-interactive --force || \
            python "$PROJECT_DIR/tools/generate_env.py" --non-interactive --force
        fi
    else
        python3 "$PROJECT_DIR/tools/generate_env.py" --non-interactive || \
        python "$PROJECT_DIR/tools/generate_env.py" --non-interactive
    fi

    step "2/3 Building and starting Docker services..."
    check_prereqs
    check_ports
    cd "$PROJECT_DIR"
    local compose_cmd
    compose_cmd="$(get_compose_cmd)"
    $compose_cmd up -d --build

    step "3/3 Health check..."
    do_healthcheck
    show_admin_password

    echo ""
    info "PyGBSentry is now running!"
    info "Web UI: http://localhost"
    info "API Docs: http://localhost:8000/docs (if ENABLE_OPENAPI_DOCS=true)"
    info "Default login: admin / (see password above)"
}

# ---------------------------------------------------------------------------
# doctor: 部署诊断
# ---------------------------------------------------------------------------
do_doctor() {
    echo ""
    step "Running deployment diagnostics..."
    echo ""

    local pass=0
    local fail=0
    local warnings=0

    # 1. Docker
    if command -v docker &>/dev/null; then
        info "[PASS] Docker is installed: $(docker --version)"
        pass=$((pass + 1))
    else
        echo -e "${RED}[FAIL]${NC} Docker is not installed. Install from https://docs.docker.com/get-docker/"
        fail=$((fail + 1))
    fi

    # 2. docker-compose
    local compose_cmd
    compose_cmd="$(get_compose_cmd)"
    if [[ -n "$compose_cmd" ]]; then
        info "[PASS] Docker Compose is available: $compose_cmd"
        pass=$((pass + 1))
    else
        echo -e "${RED}[FAIL]${NC} Docker Compose is not installed."
        fail=$((fail + 1))
    fi

    # 3. .env file
    if [[ -f "$PROJECT_DIR/backend/.env" ]]; then
        info "[PASS] backend/.env exists"
        pass=$((pass + 1))
        # Check critical vars
        for var in SECRET_KEY FIELD_ENCRYPTION_KEY MEDIA_SERVER_SECRET SIP_DEFAULT_PASSWORD DATABASE_PASSWORD REDIS_PASSWORD BACKEND_PUBLIC_HOST; do
            val=$(grep -E "^${var}=" "$PROJECT_DIR/backend/.env" 2>/dev/null | head -1 | cut -d'=' -f2- | tr -d '"' || true)
            if [[ -z "$val" || "$val" == "CHANGE_ME"* || "$val" == *"CHANGE_ME"* ]]; then
                echo -e "${RED}[FAIL]${NC} $var is not set or still has placeholder value in .env"
                fail=$((fail + 1))
            fi
        done
    else
        echo -e "${RED}[FAIL]${NC} backend/.env does not exist. Run: ./deploy/setup.sh init"
        fail=$((fail + 1))
    fi

    # 4. Port availability
    local ports=(80 8000 5060 8880 1935 554)
    for port in "${ports[@]}"; do
        if ss -tlnp 2>/dev/null | grep -q ":${port} " || \
           netstat -tlnp 2>/dev/null | grep -q ":${port} " 2>/dev/null; then
            # Check if it's our container
            if docker ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
                info "[PASS] Port $port is in use by Docker container"
                pass=$((pass + 1))
            else
                echo -e "${YELLOW}[WARN]${NC} Port $port is in use by another process"
                warnings=$((warnings + 1))
            fi
        else
            info "[PASS] Port $port is available"
            pass=$((pass + 1))
        fi
    done

    # 5. Docker containers status
    if [[ -n "$compose_cmd" ]] && [[ -f "$PROJECT_DIR/docker-compose.yml" ]]; then
        cd "$PROJECT_DIR"
        local running
        running=$($compose_cmd ps --services --filter "status=running" 2>/dev/null | wc -l || echo "0")
        local total
        total=$($compose_cmd ps --services 2>/dev/null | wc -l || echo "0")
        if [[ "$running" -eq "$total" ]] && [[ "$total" -gt 0 ]]; then
            info "[PASS] All $total Docker services are running"
            pass=$((pass + 1))
        elif [[ "$running" -gt 0 ]]; then
            echo -e "${YELLOW}[WARN]${NC} $running/$total Docker services are running"
            warnings=$((warnings + 1))
        else
            echo -e "${RED}[FAIL]${NC} No Docker services are running. Run: ./deploy/setup.sh start"
            fail=$((fail + 1))
        fi
    fi

    # 6. Backend health
    if curl -sf http://localhost:8000/api/v1/health/ &>/dev/null; then
        info "[PASS] Backend API is healthy"
        pass=$((pass + 1))
    else
        echo -e "${YELLOW}[WARN]${NC} Backend API is not responding"
        warnings=$((warnings + 1))
    fi

    # 7. Frontend
    if curl -sf http://localhost/ &>/dev/null; then
        info "[PASS] Frontend is accessible"
        pass=$((pass + 1))
    else
        echo -e "${YELLOW}[WARN]${NC} Frontend is not accessible"
        warnings=$((warnings + 1))
    fi

    # 8. SIP port
    if ss -tlnp 2>/dev/null | grep -q ":5060 " || \
       netstat -tlnp 2>/dev/null | grep -q ":5060 " 2>/dev/null; then
        info "[PASS] SIP port 5060 is listening"
        pass=$((pass + 1))
    else
        echo -e "${YELLOW}[WARN]${NC} SIP port 5060 is not listening (SIP service may not be started)"
        warnings=$((warnings + 1))
    fi

    # 9. ZLM API
    if curl -sf http://localhost:8880/index/api/getServerConfig &>/dev/null; then
        info "[PASS] ZLMediaKit API is accessible"
        pass=$((pass + 1))
    else
        echo -e "${YELLOW}[WARN]${NC} ZLMediaKit API is not accessible (may still be starting up)"
        warnings=$((warnings + 1))
    fi

    # Summary
    echo ""
    echo "──────────────────────────────────"
    echo -e "  ${GREEN}PASS${NC}: $pass  ${YELLOW}WARN${NC}: $warnings  ${RED}FAIL${NC}: $fail"
    echo "──────────────────────────────────"
    if [[ $fail -gt 0 ]]; then
        error "Deployment has $fail critical issue(s). Please fix them before proceeding."
    elif [[ $warnings -gt 0 ]]; then
        warn "Deployment has $warnings warning(s). Services may not work correctly."
    else
        info "All checks passed! Deployment is healthy."
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
case "${1:-}" in
    init)
        do_init
        ;;
    start)
        check_prereqs
        check_ports
        cd "$PROJECT_DIR"
        $(get_compose_cmd) up -d --build
        do_healthcheck
        show_admin_password
        ;;
    stop)
        cd "$PROJECT_DIR"
        $(get_compose_cmd) down
        info "Services stopped"
        ;;
    restart)
        cd "$PROJECT_DIR"
        $(get_compose_cmd) restart
        do_healthcheck
        ;;
    status)
        cd "$PROJECT_DIR"
        $(get_compose_cmd) ps
        curl -sf http://localhost:8000/api/v1/health/ 2>/dev/null && echo "" || warn "Backend not responding"
        ;;
    logs)
        cd "$PROJECT_DIR"
        $(get_compose_cmd) logs -f "${2:-}"
        ;;
    doctor)
        do_doctor
        ;;
    *)
        echo "PyGBSentry Deployment Tool"
        echo ""
        echo "Usage: $0 {init|start|stop|restart|status|logs|doctor} [service]"
        echo ""
        echo "Commands:"
        echo "  init     Generate .env with secure keys and start all services (first-time setup)"
        echo "  start    Build and start all services"
        echo "  stop     Stop all services"
        echo "  restart  Restart all services"
        echo "  status   Show service status"
        echo "  logs     Follow logs (optional: service name)"
        echo "  doctor   Run deployment diagnostics (ports, health, config validation)"
        echo ""
        echo "Quick start:"
        echo "  ./deploy/setup.sh init    # First time setup"
        echo "  ./deploy/setup.sh doctor  # Check deployment health"
        exit 1
        ;;
esac

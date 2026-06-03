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

check_command() {
    if ! command -v "$1" &>/dev/null; then
        error "$1 is required but not installed. Please install it first."
    fi
}

check_commands() {
    check_command docker
    check_command docker-compose || check_command "docker compose"
}

generate_password() {
    openssl rand -base64 24 | tr -d '/+=' | head -c 24
}

setup_env() {
    local env_file="$PROJECT_DIR/backend/.env"
    if [[ ! -f "$env_file" ]]; then
        if [[ -f "${env_file}.example" ]]; then
            cp "${env_file}.example" "$env_file"
            info "Copied .env.example to .env"
        else
            touch "$env_file"
            info "Created empty .env"
        fi
    fi

    local pg_pass
    pg_pass=$(generate_password)
    local redis_pass
    redis_pass=$(generate_password)
    local secret_key
    secret_key=$(openssl rand -hex 32)

    if ! grep -q "^POSTGRES_PASSWORD=" "$env_file" || grep -q "^POSTGRES_PASSWORD=$" "$env_file"; then
        sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${pg_pass}|" "$env_file" 2>/dev/null || \
            echo "POSTGRES_PASSWORD=${pg_pass}" >> "$env_file"
    fi
    if ! grep -q "^REDIS_PASSWORD=" "$env_file" || grep -q "^REDIS_PASSWORD=$" "$env_file"; then
        sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${redis_pass}|" "$env_file" 2>/dev/null || \
            echo "REDIS_PASSWORD=${redis_pass}" >> "$env_file"
    fi
    if ! grep -q "^SECRET_KEY=" "$env_file" || grep -q "^SECRET_KEY=$" "$env_file"; then
        sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${secret_key}|" "$env_file" 2>/dev/null || \
            echo "SECRET_KEY=${secret_key}" >> "$env_file"
    fi

    info "Environment configured with secure defaults"
}

setup_docker_compose() {
    local compose_file="$PROJECT_DIR/docker-compose.yml"
    if [[ ! -f "$compose_file" ]]; then
        error "docker-compose.yml not found at $compose_file"
    fi
    info "Using existing docker-compose.yml"
}

start_services() {
    info "Building and starting PyGBSentry..."
    cd "$PROJECT_DIR"

    if docker compose version &>/dev/null; then
        docker compose up -d --build
    elif command -v docker-compose &>/dev/null; then
        docker-compose up -d --build
    else
        error "Neither 'docker compose' nor 'docker-compose' found"
    fi

    info "Waiting for services to be healthy..."
    sleep 10
}

show_status() {
    info "PyGBSentry is starting up!"
    echo ""
    echo "  Frontend:  http://localhost"
    echo "  Backend:   http://localhost:8000"
    echo "  API Docs:  http://localhost:8000/docs"
    echo "  SIP:       udp://localhost:5060"
    echo "  ZLM HTTP:  http://localhost:8880"
    echo ""
    warn "Default admin password is printed in the backend container logs."
    warn "Run: docker compose logs backend | grep 'Auto-generated admin password'"
    echo ""
    info "To stop: docker compose down"
}

main() {
    echo "========================================="
    echo "  PyGBSentry - One-Click Setup"
    echo "========================================="
    echo ""

    check_commands
    setup_env
    setup_docker_compose
    start_services
    show_status
}

main "$@"

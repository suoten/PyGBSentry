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
    if ! docker compose version &>/dev/null && ! command -v docker-compose &>/dev/null; then
        error "docker compose (or docker-compose) is required but not installed. Please install it first."
    fi
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
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://localhost:8000/api/v1/health/ >/dev/null 2>&1; then
            info "Backend is healthy!"
            break
        fi
        attempt=$((attempt + 1))
        info "Waiting for backend health check... ($attempt/$max_attempts)"
        sleep 2
    done
    if [ $attempt -ge $max_attempts ]; then
        warn "Backend health check did not pass within $((max_attempts * 2))s. Check logs: docker compose logs backend"
    fi
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

setup_ssl() {
    echo ""
    echo "========================================="
    echo "  SSL Certificate Setup (Optional)"
    echo "========================================="
    echo ""
    read -rp "Set up HTTPS with Let's Encrypt now? [y/N] " setup_ssl_choice
    if [[ "${setup_ssl_choice,,}" != "y" ]]; then
        info "Skipping SSL setup. You can run it later: deploy/scripts/setup-ssl-certbot.sh --domain your-domain.com"
        return
    fi

    local ssl_script="${SCRIPT_DIR}/scripts/setup-ssl-certbot.sh"
    if [[ ! -f "${ssl_script}" ]]; then
        warn "SSL setup script not found: ${ssl_script}"
        return
    fi
    chmod +x "${ssl_script}"

    read -rp "Enter your domain name (e.g. pygbsentry.example.com): " ssl_domain
    if [[ -z "${ssl_domain}" ]]; then
        warn "No domain provided, skipping SSL setup."
        return
    fi

    read -rp "Enter your email for Let's Encrypt notifications (optional): " ssl_email
    local ssl_args=(--domain "${ssl_domain}")
    if [[ -n "${ssl_email}" ]]; then
        ssl_args+=(--email "${ssl_email}")
    fi

    info "Running SSL setup..."
    if "${ssl_script}" "${ssl_args[@]}"; then
        info "SSL certificate obtained. Updating nginx.conf..."
        sed -i "s/YOUR_DOMAIN/${ssl_domain}/g" "${PROJECT_DIR}/frontend/nginx.conf" 2>/dev/null || \
            warn "Could not auto-update nginx.conf. Replace YOUR_DOMAIN manually."

        info "Installing auto-renewal cron job..."
        "${ssl_script}" --install-cron 2>/dev/null || warn "Could not install cron job. Run: ${ssl_script} --install-cron"

        info "SSL setup complete! Restart frontend to apply changes:"
        info "  docker compose restart frontend"
    else
        warn "SSL setup failed. You can retry manually: ${ssl_script} --domain ${ssl_domain}"
    fi
}

setup_logrotate() {
    # P1-35: optionally install logrotate config for systemd/host deployments.
    # Only acts when /etc/logrotate.d exists; silently skipped otherwise (e.g.
    # containers without logrotate). Non-fatal on any failure.
    local conf_src="${SCRIPT_DIR}/scripts/logrotate-pygbsentry.conf"
    local logrotate_dir="/etc/logrotate.d"
    local target="${logrotate_dir}/pygbsentry"

    if [[ ! -d "${logrotate_dir}" ]]; then
        info "Skipping logrotate setup: ${logrotate_dir} not found (logrotate not installed on this host)."
        return
    fi
    if [[ ! -f "${conf_src}" ]]; then
        warn "logrotate config not found: ${conf_src}"
        return
    fi
    if cp "${conf_src}" "${target}" 2>/dev/null; then
        chmod 0644 "${target}" 2>/dev/null || true
        info "Installed logrotate config to ${target}"
        info "  Verify (dry run): sudo logrotate -d ${target}"
    else
        warn "Failed to install logrotate config to ${target} (need root? try: sudo cp ${conf_src} ${target})"
    fi
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
    setup_logrotate
    setup_ssl
}

main "$@"

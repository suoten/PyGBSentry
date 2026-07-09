#!/usr/bin/env bash
# -------------------------------------------------------------------------
# PyGBSentry SSL Certificate Automation (Let's Encrypt / certbot)
# -------------------------------------------------------------------------
# Usage:
#   ./setup-ssl-certbot.sh --domain example.com [--email admin@example.com] [--dry-run]
#   ./setup-ssl-certbot.sh --renew          # Manual renewal (usually via cron)
#   ./setup-ssl-certbot.sh --install-cron   # Install auto-renewal cron job
#
# Prerequisites:
#   - certbot installed (apt install certbot / pip install certbot)
#   - nginx stopped or port 80 free (for standalone mode)
#   - OR nginx running with /.well-known/acme-challenge/ configured (webroot mode)
#
# Environment variables:
#   CERTBOT_WEBROOT  - Webroot for challenge (default: /var/www/certbot)
#   CERTBOT_CONFIG_DIR - certbot config dir (default: /etc/letsencrypt)
#   NGINX_CONTAINER   - Docker container name for nginx reload (default: pygbsentry-frontend)
# ------------------------------------------------------------------------- 

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# --- Defaults ---
CERTBOT_WEBROOT="${CERTBOT_WEBROOT:-/var/www/certbot}"
CERTBOT_CONFIG_DIR="${CERTBOT_CONFIG_DIR:-/etc/letsencrypt}"
NGINX_CONTAINER="${NGINX_CONTAINER:-pygbsentry-frontend}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
DOMAIN=""
DRY_RUN=false
MODE=""

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)    DOMAIN="$2"; shift 2 ;;
        --email)     CERTBOT_EMAIL="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true; shift ;;
        --renew)     MODE="renew"; shift ;;
        --install-cron) MODE="install-cron"; shift ;;
        --help|-h)
            cat <<EOF
PyGBSentry SSL Certificate Automation (Let's Encrypt)

Usage:
  $0 --domain example.com [--email admin@example.com] [--dry-run]
  $0 --renew
  $0 --install-cron

Options:
  --domain DOMAIN    Domain name for the certificate (required for initial setup)
  --email EMAIL      Email for Let's Encrypt notifications (recommended)
  --dry-run          Test without actually requesting certificates
  --renew            Renew existing certificates
  --install-cron     Install daily auto-renewal cron job
  --help             Show this help message

Environment:
  CERTBOT_WEBROOT      Webroot path (default: /var/www/certbot)
  CERTBOT_CONFIG_DIR   Config directory (default: /etc/letsencrypt)
  NGINX_CONTAINER      Docker nginx container name (default: pygbsentry-frontend)
  CERTBOT_EMAIL        Fallback email if --email not given
EOF
            exit 0
            ;;
        *)  error "Unknown option: $1 (use --help)" ;;
    esac
done

# --- Check prerequisites ---
check_prerequisites() {
    if ! command -v certbot &>/dev/null; then
        error "certbot is not installed. Install it first:
  apt install certbot        # Debian/Ubuntu
  yum install certbot        # CentOS/RHEL
  pip install certbot        # Universal"
    fi
    info "certbot found: $(certbot --version 2>&1)"
}

# --- Reload nginx (Docker or native) ---
reload_nginx() {
    if command -v docker &>/dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${NGINX_CONTAINER}$"; then
        info "Reloading nginx in Docker container: ${NGINX_CONTAINER}"
        docker exec "${NGINX_CONTAINER}" nginx -s reload
    elif command -v nginx &>/dev/null; then
        info "Reloading native nginx"
        nginx -s reload
    else
        warn "Could not reload nginx automatically. Please reload nginx manually after certificate deployment."
    fi
}

# --- Request certificate ---
request_certificate() {
    if [[ -z "${DOMAIN}" ]]; then
        error "--domain is required for certificate request. Use --help for usage."
    fi

    info "Requesting Let's Encrypt certificate for: ${DOMAIN}"

    local cmd=(
        certbot certonly
        --webroot
        --webroot-path "${CERTBOT_WEBROOT}"
        -d "${DOMAIN}"
        --non-interactive
        --agree-tos
        --keep-until-expiring
    )

    if [[ -n "${CERTBOT_EMAIL}" ]]; then
        cmd+=(--email "${CERTBOT_EMAIL}")
    else
        warn "No email provided. Using --register-unsafely-without-email (not recommended for production)"
        cmd+=(--register-unsafely-without-email)
    fi

    if [[ "${DRY_RUN}" == true ]]; then
        info "[DRY-RUN] Running certbot with --dry-run flag"
        cmd+=(--dry-run)
    fi

    info "Running: ${cmd[*]}"
    "${cmd[@]}"

    if [[ "${DRY_RUN}" == true ]]; then
        info "[DRY-RUN] Test completed successfully. Remove --dry-run to request real certificate."
        return
    fi

    # Verify certificate files exist
    local cert_path="${CERTBOT_CONFIG_DIR}/live/${DOMAIN}/fullchain.pem"
    local key_path="${CERTBOT_CONFIG_DIR}/live/${DOMAIN}/privkey.pem"
    if [[ ! -f "${cert_path}" ]] || [[ ! -f "${key_path}" ]]; then
        error "Certificate files not found at expected location:
  ${cert_path}
  ${key_path}"
    fi

    info "Certificate deployed successfully:"
    info "  cert: ${cert_path}"
    info "  key:  ${key_path}"

    # Reload nginx to pick up the new certificate
    reload_nginx

    info "SSL setup complete! Update nginx.conf with your domain:"
    info "  sed -i 's/YOUR_DOMAIN/${DOMAIN}/g' frontend/nginx.conf"
    info "  (or set DOMAIN env in docker-compose.yml)"
}

# --- Renew certificates ---
renew_certificates() {
    info "Renewing Let's Encrypt certificates..."

    local cmd=(certbot renew --non-interactive)

    if [[ "${DRY_RUN}" == true ]]; then
        info "[DRY-RUN] Running certbot renew with --dry-run flag"
        cmd+=(--dry-run)
    fi

    "${cmd[@]}"

    if [[ "${DRY_RUN}" == true ]]; then
        info "[DRY-RUN] Renewal test completed."
        return
    fi

    # Reload nginx after renewal
    reload_nginx
    info "Certificate renewal complete."
}

# --- Install cron job for auto-renewal ---
install_cron() {
    local cron_script="/usr/local/bin/pygbsentry-certbot-renew.sh"
    local cron_entry="0 3 * * * ${cron_script} >> /var/log/pygbsentry-certbot-renew.log 2>&1"

    # Create the renewal script
    cat > "${cron_script}" <<EOF
#!/usr/bin/env bash
# Auto-generated by PyGBSentry setup-ssl-certbot.sh
# Renews Let's Encrypt certificates and reloads nginx
set -euo pipefail
certbot renew --non-interactive --deploy-hook "docker exec ${NGINX_CONTAINER} nginx -s reload 2>/dev/null || nginx -s reload 2>/dev/null || true"
EOF
    chmod +x "${cron_script}"
    info "Created renewal script: ${cron_script}"

    # Install cron entry (removes existing entry first)
    local cron_marker="# pygbsentry-certbot-renew"
    (crontab -l 2>/dev/null | grep -v "${cron_marker}" | grep -v "${cron_script}"; echo "${cron_entry} ${cron_marker}") | crontab -
    info "Installed daily cron job (runs at 03:00)"
    info "certbot renew will only request new certs when <= 30 days remain (default)"

    # Also install systemd timer if systemd is available
    if command -v systemctl &>/dev/null; then
        local timer_name="pygbsentry-certbot-renew"
        cat > "/etc/systemd/system/${timer_name}.timer" <<EOF
[Unit]
Description=PyGBSentry Let's Encrypt certificate renewal

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF
        cat > "/etc/systemd/system/${timer_name}.service" <<EOF
[Unit]
Description=PyGBSentry Let's Encrypt certificate renewal
After=network.target

[Service]
Type=oneshot
ExecStart=${cron_script}
EOF
        systemctl daemon-reload
        systemctl enable "${timer_name}.timer" 2>/dev/null && \
            systemctl start "${timer_name}.timer" 2>/dev/null && \
            info "Installed systemd timer: ${timer_name}.timer"
    fi
}

# --- Main ---
check_prerequisites

case "${MODE}" in
    renew)        renew_certificates ;;
    install-cron) install_cron ;;
    *)            request_certificate ;;
esac

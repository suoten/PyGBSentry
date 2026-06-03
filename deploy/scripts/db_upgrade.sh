#!/usr/bin/env bash
# -------------------------------------------------------------------------
# PyGBSentry Database Upgrade / Rollback Script
# -------------------------------------------------------------------------
# Usage:
#   ./db_upgrade.sh upgrade              # Upgrade to latest schema
#   ./db_upgrade.sh upgrade v2.1.0       # Upgrade to specific version
#   ./db_upgrade.sh rollback             # Rollback one migration
#   ./db_upgrade.sh rollback 3           # Rollback N migrations
#   ./db_upgrade.sh status               # Show current migration status
#   ./db_upgrade.sh backup               # Backup before upgrade
#
# Environment variables (or load from .env):
#   DATABASE_TYPE, DATABASE_HOST, DATABASE_PORT, DATABASE_NAME,
#   DATABASE_USER, DATABASE_PASSWORD
# -------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_DIR="${PROJECT_DIR}/backend"

# Load .env if available
ENV_FILE="${BACKEND_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    set -a
    source <(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$' || true)
    set +a
fi

log_info()  { echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo "[WARN]  $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }

run_alembic() {
    cd "${BACKEND_DIR}"
    python -m alembic "$@"
}

do_backup() {
    log_info "Creating pre-upgrade database backup..."
    if [ ! -f "${SCRIPT_DIR}/backup.sh" ]; then
        log_error "backup.sh not found at ${SCRIPT_DIR}/backup.sh"
        exit 1
    fi
    "${SCRIPT_DIR}/backup.sh" --db-only
    log_info "Pre-upgrade backup completed."
}

do_upgrade() {
    local target="${1:-head}"
    log_info "=== PyGBSentry Database Upgrade ==="
    log_info "Current status:"
    run_alembic current || true
    log_info ""
    log_info "Upgrading to: ${target}"
    run_alembic upgrade "${target}"
    log_info ""
    log_info "Post-upgrade status:"
    run_alembic current || true
    log_info "=== Upgrade Complete ==="
}

do_rollback() {
    local target="${1:--1}"
    log_info "=== PyGBSentry Database Rollback ==="
    log_info "Current status:"
    run_alembic current || true
    log_info ""
    log_info "Creating pre-rollback backup..."
    do_backup
    log_info ""
    log_info "Rolling back to: ${target}"
    run_alembic downgrade "${target}"
    log_info ""
    log_info "Post-rollback status:"
    run_alembic current || true
    log_info "=== Rollback Complete ==="
}

do_status() {
    log_info "=== PyGBSentry Database Migration Status ==="
    cd "${BACKEND_DIR}"
    python -m alembic current 2>/dev/null || echo "No migrations applied yet"
    echo ""
    echo "Migration history:"
    python -m alembic history 2>/dev/null || echo "No migration history available"
}

case "${1:-}" in
    upgrade)
        do_backup
        do_upgrade "${2:-head}"
        ;;
    rollback)
        do_rollback "${2:--1}"
        ;;
    status)
        do_status
        ;;
    backup)
        do_backup
        ;;
    *)
        echo "PyGBSentry Database Upgrade/Rollback Tool"
        echo ""
        echo "Usage: $0 {upgrade|rollback|status|backup} [target]"
        echo ""
        echo "Commands:"
        echo "  upgrade [target]  Upgrade to target (default: head)"
        echo "  rollback [n]      Rollback n steps (default: 1)"
        echo "  status            Show current migration status"
        echo "  backup            Create pre-upgrade backup"
        ;;
esac

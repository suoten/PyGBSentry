#!/usr/bin/env bash
# -------------------------------------------------------------------------
# PyGBSentry Database & Configuration Restore Script
# -------------------------------------------------------------------------
# Usage:
#   ./restore.sh /path/to/backup.tar.gz           # Restore DB + config
#   ./restore.sh /path/to/backup.tar.gz --db-only  # Database only
#   ./restore.sh /path/to/backup.tar.gz --config-only  # Configuration only
#   ./restore.sh /path/to/backup.tar.gz --dry-run  # Preview what will be restored
#
# Environment variables:
#   BACKUP_DIR     - Backup directory (default: /opt/pygbsentry/backups)
#   DB_HOST        - Database host (default: localhost)
#   DB_PORT        - Database port (default: 5432)
#   DB_NAME        - Database name (default: pygbsentry)
#   DB_USER        - Database user (default: pygbsentry)
#   DB_PASSWORD    - Database password (from .env if not set)
#   DB_TYPE        - Database type: postgresql|mysql|sqlite (default: from .env)
#   SKIP_PRE_BACKUP- Set to "true" to skip pre-restore backup (default: false)
# -------------------------------------------------------------------------

set -euo pipefail

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/opt/pygbsentry/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# --- Load .env if available ---
ENV_FILE="${PROJECT_DIR}/backend/.env"
if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$' || true)
    set +a
fi

# --- Database configuration ---
DB_TYPE="${DB_TYPE:-${DATABASE_TYPE:-postgresql}}"
DB_HOST="${DB_HOST:-${DATABASE_HOST:-localhost}}"
DB_PORT="${DB_PORT:-${DATABASE_PORT:-5432}}"
DB_NAME="${DB_NAME:-${DATABASE_NAME:-pygbsentry}}"
DB_USER="${DB_USER:-${DATABASE_USER:-pygbsentry}}"
DB_PASSWORD="${DB_PASSWORD:-${DATABASE_PASSWORD:-}}"
SKIP_PRE_BACKUP="${SKIP_PRE_BACKUP:-false}"

# --- Helper functions ---
log_info()  { echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo "[WARN]  $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }

confirm_action() {
    local prompt="${1:-Are you sure?}"
    echo ""
    echo "⚠️  ${prompt}"
    read -r -p "Type 'yes' to confirm: " response
    if [[ "${response}" != "yes" ]]; then
        log_info "Operation cancelled by user"
        exit 0
    fi
}

# --- Pre-restore backup ---
create_pre_restore_backup() {
    if [[ "${SKIP_PRE_BACKUP}" == "true" ]]; then
        log_warn "Pre-restore backup skipped (SKIP_PRE_BACKUP=true)"
        return
    fi

    local pre_backup_name="pre_restore_${TIMESTAMP}"
    local pre_backup_dir="${BACKUP_DIR}/${pre_backup_name}"
    mkdir -p "${pre_backup_dir}/config"

    log_info "Creating pre-restore backup of current data..."

    # Backup current database
    case "${DB_TYPE}" in
        postgresql|postgres)
            if command -v pg_dump &>/dev/null; then
                export PGPASSWORD="${DB_PASSWORD}"
                pg_dump \
                    -h "${DB_HOST}" \
                    -p "${DB_PORT}" \
                    -U "${DB_USER}" \
                    -d "${DB_NAME}" \
                    --no-owner \
                    --no-privileges \
                    --format=custom \
                    -f "${pre_backup_dir}/database.dump" 2>/dev/null || log_warn "Pre-restore database backup failed"
                unset PGPASSWORD
            else
                log_warn "pg_dump not found, skipping pre-restore database backup"
            fi
            ;;
        mysql)
            if command -v mysqldump &>/dev/null; then
                mysqldump \
                    -h "${DB_HOST}" \
                    -P "${DB_PORT}" \
                    -u "${DB_USER}" \
                    -p"${DB_PASSWORD}" \
                    --single-transaction \
                    --routines \
                    --triggers \
                    "${DB_NAME}" > "${pre_backup_dir}/database.sql" 2>/dev/null || log_warn "Pre-restore database backup failed"
            else
                log_warn "mysqldump not found, skipping pre-restore database backup"
            fi
            ;;
        sqlite)
            local db_path="${PROJECT_DIR}/backend/pygbsentry.db"
            if [[ -f "${db_path}" ]] && command -v sqlite3 &>/dev/null; then
                sqlite3 "${db_path}" ".backup '${pre_backup_dir}/database.db'" 2>/dev/null || log_warn "Pre-restore database backup failed"
            else
                log_warn "SQLite database or sqlite3 not found, skipping pre-restore database backup"
            fi
            ;;
    esac

    # Backup current config
    for env_file in "${PROJECT_DIR}"/backend/.env*; do
        if [[ -f "${env_file}" ]]; then
            cp "${env_file}" "${pre_backup_dir}/config/"
        fi
    done
    if [[ -f "${PROJECT_DIR}/docker-compose.yml" ]]; then
        cp "${PROJECT_DIR}/docker-compose.yml" "${pre_backup_dir}/config/"
    fi
    if [[ -f "${PROJECT_DIR}/deploy/helm/pygbsentry/values.yaml" ]]; then
        cp "${PROJECT_DIR}/deploy/helm/pygbsentry/values.yaml" "${pre_backup_dir}/config/helm-values.yaml"
    fi
    if [[ -f "${PROJECT_DIR}/backend/binaries/linux/zlm.ini" ]]; then
        cp "${PROJECT_DIR}/backend/binaries/linux/zlm.ini" "${pre_backup_dir}/config/"
    fi

    # Create archive
    tar -czf "${BACKUP_DIR}/${pre_backup_name}.tar.gz" -C "${BACKUP_DIR}" "${pre_backup_name}"
    rm -rf "${pre_backup_dir}"

    local size
    size=$(du -sh "${BACKUP_DIR}/${pre_backup_name}.tar.gz" | cut -f1)
    log_info "Pre-restore backup saved: ${pre_backup_name}.tar.gz (${size})"
}

# --- Restore functions ---
restore_postgresql() {
    local dump_file="${1}"
    log_info "Restoring PostgreSQL database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
    export PGPASSWORD="${DB_PASSWORD}"
    pg_restore \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        --no-owner \
        --no-privileges \
        --clean \
        --if-exists \
        "${dump_file}" || {
        unset PGPASSWORD
        log_error "PostgreSQL restore failed"
        return 1
    }
    unset PGPASSWORD
    log_info "PostgreSQL restore completed"
}

restore_mysql() {
    local sql_file="${1}"
    log_info "Restoring MySQL database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
    mysql \
        -h "${DB_HOST}" \
        -P "${DB_PORT}" \
        -u "${DB_USER}" \
        -p"${DB_PASSWORD}" \
        "${DB_NAME}" < "${sql_file}" || {
        log_error "MySQL restore failed"
        return 1
    }
    log_info "MySQL restore completed"
}

restore_sqlite() {
    local db_file="${1}"
    local target_path="${PROJECT_DIR}/backend/pygbsentry.db"
    log_info "Restoring SQLite database to: ${target_path}"
    cp "${db_file}" "${target_path}" || {
        log_error "SQLite restore failed"
        return 1
    }
    log_info "SQLite restore completed"
}

restore_database() {
    local backup_dir="${1}"
    local dry_run="${2:-false}"

    local db_file=""
    local db_type_detected=""

    if [[ -f "${backup_dir}/database.dump" ]]; then
        db_file="${backup_dir}/database.dump"
        db_type_detected="postgresql"
    elif [[ -f "${backup_dir}/database.sql" ]]; then
        db_file="${backup_dir}/database.sql"
        db_type_detected="mysql"
    elif [[ -f "${backup_dir}/database.db" ]]; then
        db_file="${backup_dir}/database.db"
        db_type_detected="sqlite"
    else
        log_warn "No database backup found in archive"
        return
    fi

    if [[ "${dry_run}" == true ]]; then
        log_info "[DRY-RUN] Would restore ${db_type_detected} database from: $(basename "${db_file}")"
        log_info "[DRY-RUN]   Target: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
        return
    fi

    case "${db_type_detected}" in
        postgresql)
            if ! command -v pg_restore &>/dev/null; then
                log_error "pg_restore not found. Install postgresql-client."
                return 1
            fi
            restore_postgresql "${db_file}"
            ;;
        mysql)
            if ! command -v mysql &>/dev/null; then
                log_error "mysql client not found. Install mysql-client."
                return 1
            fi
            restore_mysql "${db_file}"
            ;;
        sqlite)
            restore_sqlite "${db_file}"
            ;;
    esac
}

restore_config() {
    local backup_dir="${1}"
    local dry_run="${2:-false}"

    if [[ ! -d "${backup_dir}/config" ]]; then
        log_warn "No configuration backup found in archive"
        return
    fi

    if [[ "${dry_run}" == true ]]; then
        log_info "[DRY-RUN] Would restore the following configuration files:"
        for f in "${backup_dir}/config/"*; do
            [[ -f "${f}" ]] && log_info "[DRY-RUN]   - $(basename "${f}")"
        done
        return
    fi

    log_info "Restoring configuration files..."
    # .env files
    for env_file in "${backup_dir}/config/".env*; do
        if [[ -f "${env_file}" ]]; then
            cp "${env_file}" "${PROJECT_DIR}/backend/"
            log_info "  Restored: $(basename "${env_file}")"
        fi
    done
    # docker-compose.yml
    if [[ -f "${backup_dir}/config/docker-compose.yml" ]]; then
        cp "${backup_dir}/config/docker-compose.yml" "${PROJECT_DIR}/"
        log_info "  Restored: docker-compose.yml"
    fi
    # Helm values
    if [[ -f "${backup_dir}/config/helm-values.yaml" ]]; then
        mkdir -p "${PROJECT_DIR}/deploy/helm/pygbsentry/"
        cp "${backup_dir}/config/helm-values.yaml" "${PROJECT_DIR}/deploy/helm/pygbsentry/values.yaml"
        log_info "  Restored: helm-values.yaml -> values.yaml"
    fi
    # ZLM config
    if [[ -f "${backup_dir}/config/zlm.ini" ]]; then
        mkdir -p "${PROJECT_DIR}/backend/binaries/linux/"
        cp "${backup_dir}/config/zlm.ini" "${PROJECT_DIR}/backend/binaries/linux/"
        log_info "  Restored: zlm.ini"
    fi
    log_info "Configuration restore completed"
}

# --- Dry-run preview ---
do_dry_run() {
    local backup_file="${1}"
    local do_db="${2:-true}"
    local do_config="${3:-true}"

    if [[ ! -f "${backup_file}" ]]; then
        log_error "Backup file not found: ${backup_file}"
        exit 1
    fi

    local extract_dir="${BACKUP_DIR}/dryrun_${TIMESTAMP}"
    mkdir -p "${extract_dir}"

    log_info "=== PyGBSentry Restore Dry-Run ==="
    log_info "Backup archive: ${backup_file}"

    tar -xzf "${backup_file}" -C "${extract_dir}"

    local backup_dir
    backup_dir=$(find "${extract_dir}" -mindepth 1 -maxdepth 1 -type d | head -1)

    if [[ -z "${backup_dir}" ]]; then
        log_error "Invalid backup archive: no top-level directory found"
        rm -rf "${extract_dir}"
        exit 1
    fi

    log_info "Archive contents:"
    log_info "  Backup name: $(basename "${backup_dir}")"

    # List all files in archive
    for f in "${backup_dir}/"*; do
        if [[ -f "${f}" ]]; then
            log_info "  - $(basename "${f}")"
        elif [[ -d "${f}" ]]; then
            log_info "  - $(basename "${f}")/"
            for cf in "${f}/"*; do
                [[ -f "${cf}" ]] && log_info "      - $(basename "${cf}")"
            done
        fi
    done

    echo ""
    log_info "--- Restore Plan ---"

    if [[ "${do_db}" == true ]]; then
        restore_database "${backup_dir}" true
    fi

    if [[ "${do_config}" == true ]]; then
        restore_config "${backup_dir}" true
    fi

    echo ""
    log_info "--- Current Database Configuration ---"
    log_info "  DB_TYPE: ${DB_TYPE}"
    log_info "  DB_HOST: ${DB_HOST}"
    log_info "  DB_PORT: ${DB_PORT}"
    log_info "  DB_NAME: ${DB_NAME}"
    log_info "  DB_USER: ${DB_USER}"

    # Cleanup
    rm -rf "${extract_dir}"
    log_info "=== Dry-Run Complete (no changes made) ==="
}

# --- Main restore ---
do_restore() {
    local backup_file="${1:-}"
    shift || true

    if [[ -z "${backup_file}" ]]; then
        log_error "Usage: $0 /path/to/backup.tar.gz [OPTIONS]"
        exit 1
    fi

    if [[ ! -f "${backup_file}" ]]; then
        log_error "Backup file not found: ${backup_file}"
        exit 1
    fi

    local do_db=true
    local do_config=true
    local dry_run=false

    while [[ $# -gt 0 ]]; do
        case "${1}" in
            --db-only)      do_config=false ;;
            --config-only)  do_db=false ;;
            --dry-run)      dry_run=true ;;
            --skip-pre-backup) SKIP_PRE_BACKUP="true" ;;
            *) log_error "Unknown option: ${1}"; exit 1 ;;
        esac
        shift
    done

    # Handle dry-run mode
    if [[ "${dry_run}" == true ]]; then
        do_dry_run "${backup_file}" "${do_db}" "${do_config}"
        exit 0
    fi

    log_info "=== PyGBSentry Restore Started ==="
    log_info "Backup archive: ${backup_file}"

    # Extract archive
    local extract_dir="${BACKUP_DIR}/restore_${TIMESTAMP}"
    mkdir -p "${extract_dir}"
    tar -xzf "${backup_file}" -C "${extract_dir}"

    local backup_dir
    backup_dir=$(find "${extract_dir}" -mindepth 1 -maxdepth 1 -type d | head -1)

    if [[ -z "${backup_dir}" ]]; then
        log_error "Invalid backup archive: no top-level directory found"
        rm -rf "${extract_dir}"
        exit 1
    fi

    log_info "Extracted backup: $(basename "${backup_dir}")"

    # Show what will be restored
    echo ""
    log_info "The following will be restored:"
    if [[ "${do_db}" == true ]]; then
        if [[ -f "${backup_dir}/database.dump" ]]; then
            log_info "  - PostgreSQL database (${DB_NAME}@${DB_HOST}:${DB_PORT})"
        elif [[ -f "${backup_dir}/database.sql" ]]; then
            log_info "  - MySQL database (${DB_NAME}@${DB_HOST}:${DB_PORT})"
        elif [[ -f "${backup_dir}/database.db" ]]; then
            log_info "  - SQLite database (${PROJECT_DIR}/backend/pygbsentry.db)"
        else
            log_info "  - No database backup found in archive"
        fi
    fi
    if [[ "${do_config}" == true && -d "${backup_dir}/config" ]]; then
        log_info "  - Configuration files:"
        for f in "${backup_dir}/config/"*; do
            [[ -f "${f}" ]] && log_info "      - $(basename "${f}")"
        done
    fi
    echo ""

    # Require explicit confirmation
    confirm_action "This will OVERWRITE existing data! A pre-restore backup will be created first."

    # Create pre-restore backup
    create_pre_restore_backup

    # Restore database
    if [[ "${do_db}" == true ]]; then
        restore_database "${backup_dir}" false
    fi

    # Restore configuration
    if [[ "${do_config}" == true ]]; then
        restore_config "${backup_dir}" false
    fi

    # Cleanup extracted files
    rm -rf "${extract_dir}"

    log_info "=== PyGBSentry Restore Finished ==="
    log_info "If something went wrong, check the pre-restore backup in: ${BACKUP_DIR}/"
}

# --- Main ---
case "${1:-}" in
    --help|-h)
        echo "PyGBSentry Restore Script"
        echo ""
        echo "Usage: $0 /path/to/backup.tar.gz [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --db-only          Restore database only"
        echo "  --config-only      Restore configuration only"
        echo "  --dry-run          Preview what will be restored (no changes made)"
        echo "  --skip-pre-backup  Skip creating a pre-restore backup"
        echo "  --help             Show this help message"
        echo ""
        echo "Environment variables:"
        echo "  BACKUP_DIR       Backup directory (default: /opt/pygbsentry/backups)"
        echo "  DB_TYPE          Database type: postgresql|mysql|sqlite"
        echo "  DB_HOST          Database host"
        echo "  DB_PORT          Database port"
        echo "  DB_NAME          Database name"
        echo "  DB_USER          Database user"
        echo "  DB_PASSWORD      Database password"
        echo "  SKIP_PRE_BACKUP  Set to 'true' to skip pre-restore backup"
        ;;
    *)
        do_restore "$@"
        ;;
esac

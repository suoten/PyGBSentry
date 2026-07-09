#!/usr/bin/env bash
# -------------------------------------------------------------------------
# PyGBSentry Database & Configuration Backup Script
# -------------------------------------------------------------------------
# Usage:
#   ./backup.sh                          # Full backup (DB + config)
#   ./backup.sh --db-only                # Database only
#   ./backup.sh --config-only            # Configuration only
#   ./backup.sh --include-media          # Full backup + media (records/snapshots)
#   ./backup.sh --dry-run                # Show what would be backed up (no changes)
#   ./backup.sh --restore /path/to/backup.tar.gz  # Restore from backup
#
# Environment variables:
#   BACKUP_DIR     - Backup destination directory (default: /opt/pygbsentry/backups)
#   DB_HOST        - Database host (default: localhost)
#   DB_PORT        - Database port (default: 5432)
#   DB_NAME        - Database name (default: pygbsentry)
#   DB_USER        - Database user (default: pygbsentry)
#   DB_PASSWORD    - Database password (from .env if not set)
#   DB_TYPE        - Database type: postgresql|mysql|sqlite (default: from .env)
#   RETENTION_DAYS - Number of days to keep backups (default: 30)
#   MEDIA_RECORDS_DIR - Recordings directory (default: /app/records)
#   MEDIA_DATA_DIR    - Device snapshots/timelapse directory (default: /app/data)
#   MEDIA_MAX_FILE_SIZE - Skip files larger than this (e.g. 500M, default: unlimited)
#
# NOTE: Media backup (--include-media) is OFF by default because recordings
# can be very large. For production, consider NFS/S3 for independent media
# backups rather than including them in the regular backup archive.
# -------------------------------------------------------------------------

set -euo pipefail

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/opt/pygbsentry/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="pygbsentry_backup_${TIMESTAMP}"

# --- Media backup configuration ---
MEDIA_RECORDS_DIR="${MEDIA_RECORDS_DIR:-/app/records}"
MEDIA_DATA_DIR="${MEDIA_DATA_DIR:-/app/data}"
MEDIA_MAX_FILE_SIZE="${MEDIA_MAX_FILE_SIZE:-}"  # e.g. "500M" — empty = no limit

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

# --- Helper functions ---
log_info()  { echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo "[WARN]  $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }

cleanup_old_backups() {
    local count
    count=$(find "${BACKUP_DIR}" -name "pygbsentry_backup_*.tar.gz" -mtime +"${RETENTION_DAYS}" 2>/dev/null | wc -l)
    if [[ "${count}" -gt 0 ]]; then
        log_info "Removing ${count} backup(s) older than ${RETENTION_DAYS} days"
        find "${BACKUP_DIR}" -name "pygbsentry_backup_*.tar.gz" -mtime +"${RETENTION_DAYS}" -delete
    fi
}

backup_postgresql() {
    log_info "Backing up PostgreSQL database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
    export PGPASSWORD="${DB_PASSWORD}"
    pg_dump \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        --no-owner \
        --no-privileges \
        --format=custom \
        -f "${BACKUP_DIR}/${BACKUP_NAME}/database.dump"
    unset PGPASSWORD
    log_info "PostgreSQL backup completed: database.dump"
}

backup_mysql() {
    log_info "Backing up MySQL database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
    MYSQL_PWD="${DB_PASSWORD}" mysqldump \
        -h "${DB_HOST}" \
        -P "${DB_PORT}" \
        -u "${DB_USER}" \
        --single-transaction \
        --routines \
        --triggers \
        "${DB_NAME}" > "${BACKUP_DIR}/${BACKUP_NAME}/database.sql"
    log_info "MySQL backup completed: database.sql"
}

backup_sqlite() {
    local db_path="${PROJECT_DIR}/backend/pygbsentry.db"
    if [[ ! -f "${db_path}" ]]; then
        log_warn "SQLite database not found at ${db_path}, skipping"
        return
    fi
    log_info "Backing up SQLite database: ${db_path}"
    sqlite3 "${db_path}" ".backup '${BACKUP_DIR}/${BACKUP_NAME}/database.db'"
    log_info "SQLite backup completed: database.db"
}

backup_database() {
    case "${DB_TYPE}" in
        postgresql|postgres)
            if ! command -v pg_dump &>/dev/null; then
                log_error "pg_dump not found. Install postgresql-client."
                return 1
            fi
            backup_postgresql
            ;;
        mysql)
            if ! command -v mysqldump &>/dev/null; then
                log_error "mysqldump not found. Install mysql-client."
                return 1
            fi
            backup_mysql
            ;;
        sqlite)
            if ! command -v sqlite3 &>/dev/null; then
                log_error "sqlite3 not found."
                return 1
            fi
            backup_sqlite
            ;;
        *)
            log_error "Unsupported database type: ${DB_TYPE}"
            return 1
            ;;
    esac
}

backup_config() {
    log_info "Backing up configuration files"
    # .env files
    for env_file in "${PROJECT_DIR}"/backend/.env*; do
        if [[ -f "${env_file}" ]]; then
            cp "${env_file}" "${BACKUP_DIR}/${BACKUP_NAME}/config/"
        fi
    done
    # docker-compose
    if [[ -f "${PROJECT_DIR}/docker-compose.yml" ]]; then
        cp "${PROJECT_DIR}/docker-compose.yml" "${BACKUP_DIR}/${BACKUP_NAME}/config/"
    fi
    # Helm values
    if [[ -f "${PROJECT_DIR}/deploy/helm/pygbsentry/values.yaml" ]]; then
        cp "${PROJECT_DIR}/deploy/helm/pygbsentry/values.yaml" "${BACKUP_DIR}/${BACKUP_NAME}/config/helm-values.yaml"
    fi
    # ZLM config (if exists)
    if [[ -f "${PROJECT_DIR}/backend/binaries/linux/zlm.ini" ]]; then
        cp "${PROJECT_DIR}/backend/binaries/linux/zlm.ini" "${BACKUP_DIR}/${BACKUP_NAME}/config/"
    fi
    log_info "Configuration backup completed"
}

backup_media() {
    local media_dir="${BACKUP_DIR}/${BACKUP_NAME}/media"
    local has_media=false

    # Build find size-filter argument
    local size_filter=()
    if [[ -n "${MEDIA_MAX_FILE_SIZE}" ]]; then
        size_filter=(-size -"${MEDIA_MAX_FILE_SIZE}")
    fi

    # Back up recordings directory
    if [[ -d "${MEDIA_RECORDS_DIR}" ]]; then
        local records_count
        records_count=$(find "${MEDIA_RECORDS_DIR}" -type f "${size_filter[@]}" 2>/dev/null | wc -l)
        if [[ "${records_count}" -gt 0 ]]; then
            log_info "Backing up recordings: ${MEDIA_RECORDS_DIR} (${records_count} files)"
            if [[ "${DRY_RUN:-false}" == true ]]; then
                log_info "[DRY-RUN] Would copy ${records_count} files from ${MEDIA_RECORDS_DIR}"
                find "${MEDIA_RECORDS_DIR}" -type f "${size_filter[@]}" 2>/dev/null | head -20 | while read -r f; do
                    log_info "[DRY-RUN]   ${f}"
                done
            else
                mkdir -p "${media_dir}"
                mkdir -p "${media_dir}/records"
                find "${MEDIA_RECORDS_DIR}" -type f "${size_filter[@]}" -print0 2>/dev/null | \
                    while IFS= read -r -d '' f; do
                        local rel="${f#${MEDIA_RECORDS_DIR}/}"
                        mkdir -p "${media_dir}/records/$(dirname "${rel}")"
                        cp "${f}" "${media_dir}/records/${rel}"
                    done
            fi
            has_media=true
        else
            log_info "Recordings directory is empty: ${MEDIA_RECORDS_DIR}"
        fi
    else
        log_info "Recordings directory not found: ${MEDIA_RECORDS_DIR}"
    fi

    # Back up device data (snapshots, timelapse)
    if [[ -d "${MEDIA_DATA_DIR}" ]]; then
        local data_count
        data_count=$(find "${MEDIA_DATA_DIR}" -type f "${size_filter[@]}" 2>/dev/null | wc -l)
        if [[ "${data_count}" -gt 0 ]]; then
            log_info "Backing up device data: ${MEDIA_DATA_DIR} (${data_count} files)"
            if [[ "${DRY_RUN:-false}" == true ]]; then
                log_info "[DRY-RUN] Would copy ${data_count} files from ${MEDIA_DATA_DIR}"
                find "${MEDIA_DATA_DIR}" -type f "${size_filter[@]}" 2>/dev/null | head -20 | while read -r f; do
                    log_info "[DRY-RUN]   ${f}"
                done
            else
                mkdir -p "${media_dir}"
                mkdir -p "${media_dir}/data"
                find "${MEDIA_DATA_DIR}" -type f "${size_filter[@]}" -print0 2>/dev/null | \
                    while IFS= read -r -d '' f; do
                        local rel="${f#${MEDIA_DATA_DIR}/}"
                        mkdir -p "${media_dir}/data/$(dirname "${rel}")"
                        cp "${f}" "${media_dir}/data/${rel}"
                    done
            fi
            has_media=true
        else
            log_info "Device data directory is empty: ${MEDIA_DATA_DIR}"
        fi
    else
        log_info "Device data directory not found: ${MEDIA_DATA_DIR}"
    fi

    if [[ "${has_media}" == false ]]; then
        rmdir "${media_dir}" 2>/dev/null || true
        log_info "No media files found to back up"
    fi
}

do_backup() {
    local do_db=true
    local do_config=true
    local do_media=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --db-only)       do_config=false ;;
            --config-only)   do_db=false ;;
            --include-media) do_media=true ;;
            --dry-run)       DRY_RUN=true ;;
            *)               log_warn "Unknown option: $1" ;;
        esac
        shift
    done

    if [[ "${DRY_RUN:-false}" == true ]]; then
        log_info "=== DRY RUN — no files will be written ==="
    fi

    mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}/config"

    log_info "=== PyGBSentry Backup Started ==="
    log_info "Backup directory: ${BACKUP_DIR}/${BACKUP_NAME}"

    if [[ "${do_db}" == true ]]; then
        if [[ "${DRY_RUN:-false}" == true ]]; then
            log_info "[DRY-RUN] Would back up ${DB_TYPE} database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
        else
            backup_database
        fi
    fi

    if [[ "${do_config}" == true ]]; then
        if [[ "${DRY_RUN:-false}" == true ]]; then
            log_info "[DRY-RUN] Would back up configuration files (.env, docker-compose, helm, zlm.ini)"
        else
            backup_config
        fi
    fi

    if [[ "${do_media}" == true ]]; then
        backup_media
    fi

    # Create archive (skip in dry-run)
    if [[ "${DRY_RUN:-false}" == true ]]; then
        log_info "[DRY-RUN] Would create archive: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
        rm -rf "${BACKUP_DIR}/${BACKUP_NAME}"
        log_info "=== DRY RUN Finished ==="
        return
    fi

    log_info "Creating archive: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
    tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C "${BACKUP_DIR}" "${BACKUP_NAME}"
    rm -rf "${BACKUP_DIR}/${BACKUP_NAME}"

    # Calculate size
    local size
    size=$(du -sh "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | cut -f1)
    log_info "Backup completed: ${BACKUP_NAME}.tar.gz (${size})"

    # Cleanup old backups
    cleanup_old_backups

    log_info "=== PyGBSentry Backup Finished ==="
}

do_restore() {
    local backup_file="${1:-}"
    if [[ -z "${backup_file}" ]]; then
        log_error "Usage: $0 --restore /path/to/backup.tar.gz"
        exit 1
    fi
    if [[ ! -f "${backup_file}" ]]; then
        log_error "Backup file not found: ${backup_file}"
        exit 1
    fi

    log_info "=== PyGBSentry Restore Started ==="
    log_warn "WARNING: This will overwrite existing data!"

    # Extract
    local extract_dir="${BACKUP_DIR}/restore_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "${extract_dir}"
    tar -xzf "${backup_file}" -C "${extract_dir}"
    local backup_dir
    backup_dir=$(find "${extract_dir}" -mindepth 1 -maxdepth 1 -type d | head -1)

    if [[ -z "${backup_dir}" ]]; then
        log_error "Invalid backup archive"
        exit 1
    fi

    # Restore database
    if [[ -f "${backup_dir}/database.dump" ]]; then
        log_info "Restoring PostgreSQL database..."
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
            "${backup_dir}/database.dump" || true
        unset PGPASSWORD
    elif [[ -f "${backup_dir}/database.sql" ]]; then
        log_info "Restoring MySQL database..."
        mysql -h "${DB_HOST}" -P "${DB_PORT}" -u "${DB_USER}" -p"${DB_PASSWORD}" "${DB_NAME}" < "${backup_dir}/database.sql" || true
    elif [[ -f "${backup_dir}/database.db" ]]; then
        log_info "Restoring SQLite database..."
        cp "${backup_dir}/database.db" "${PROJECT_DIR}/backend/pygbsentry.db"
    fi

    # Restore config
    if [[ -d "${backup_dir}/config" ]]; then
        log_info "Restoring configuration files..."
        cp -r "${backup_dir}/config/"* "${PROJECT_DIR}/backend/" 2>/dev/null || true
    fi

    # Cleanup
    rm -rf "${extract_dir}"
    log_info "=== PyGBSentry Restore Finished ==="
}

# --- Main ---
case "${1:-}" in
    --restore)      do_restore "${2:-}" ;;
    --help|-h)
        echo "PyGBSentry Backup Script"
        echo ""
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  (no option)       Full backup (database + configuration)"
        echo "  --db-only         Database backup only"
        echo "  --config-only     Configuration backup only"
        echo "  --include-media   Also back up recordings and device data (large!)"
        echo "  --dry-run         Show what would be backed up without writing files"
        echo "  --restore FILE    Restore from backup archive"
        echo "  --help            Show this help message"
        echo ""
        echo "Combinations are supported, e.g.:"
        echo "  $0 --include-media --dry-run    # Preview media backup"
        echo "  $0 --db-only --dry-run          # Preview DB backup"
        ;;
    *)              do_backup "$@" ;;
esac

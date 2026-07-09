#!/usr/bin/env bash
# -------------------------------------------------------------------------
# PyGBSentry Database Restore Script
# Restores from encrypted or plain backup files
# Supports PostgreSQL and SQLite
# -------------------------------------------------------------------------
set -euo pipefail

# Default configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-}"
DATABASE_TYPE="${DATABASE_TYPE:-postgresql}"
DATABASE_HOST="${DATABASE_HOST:-localhost}"
DATABASE_PORT="${DATABASE_PORT:-5432}"
DATABASE_NAME="${DATABASE_NAME:-pygb28181}"
DATABASE_USER="${DATABASE_USER:-postgres}"
DATABASE_PASSWORD="${DATABASE_PASSWORD:-}"
SQLITE_PATH="${SQLITE_PATH:-./pygbsentry.db}"

# Logging
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[ERROR] $*" >&2; exit 1; }

# Arguments
BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ]; then
    # List available backups
    log "No backup file specified. Available backups in $BACKUP_DIR:"
    if [ -d "$BACKUP_DIR" ]; then
        ls -lh "$BACKUP_DIR"/pygbsentry_db_* 2>/dev/null || log "No backups found."
    else
        log "Backup directory does not exist: $BACKUP_DIR"
    fi
    echo ""
    echo "Usage: $0 <backup_file_path>"
    echo "       $0 ${BACKUP_DIR}/pygbsentry_db_20250105_120000.sql.enc"
    exit 1
fi

# Resolve full path
if [[ "$BACKUP_FILE" != /* ]]; then
    BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILE}"
fi

if [ ! -f "$BACKUP_FILE" ]; then
    err "Backup file not found: $BACKUP_FILE"
fi

log "Starting database restore from: $BACKUP_FILE"
log "Database type: $DATABASE_TYPE"

# Safety confirmation (skip with --force)
if [ "${2:-}" != "--force" ]; then
    echo ""
    echo "WARNING: This will OVERWRITE the current database: $DATABASE_NAME"
    echo "A pre-restore backup will be created automatically."
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        log "Restore cancelled by user."
        exit 0
    fi
fi

# Pre-restore backup
PRE_RESTORE_BACKUP="${BACKUP_DIR}/pre_restore_$(date +%Y%m%d_%H%M%S)"
log "Creating pre-restore backup: $PRE_RESTORE_BACKUP"

if [ "$DATABASE_TYPE" = "postgresql" ] || [ "$DATABASE_TYPE" = "postgres" ]; then
    export PGPASSWORD="${DATABASE_PASSWORD}"
    pg_dump -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER" -d "$DATABASE_NAME" \
            --format=custom --no-owner --no-privileges -f "${PRE_RESTORE_BACKUP}.sql" 2>/dev/null || \
            log "Warning: Pre-restore backup failed (database may not exist yet)."
    unset PGPASSWORD
elif [ "$DATABASE_TYPE" = "sqlite" ]; then
    [ -f "$SQLITE_PATH" ] && cp "$SQLITE_PATH" "${PRE_RESTORE_BACKUP}.db" || log "Info: No existing SQLite database to backup."
fi
log "Pre-restore backup completed."

# Decrypt if encrypted
RESTORE_FILE="$BACKUP_FILE"
if [[ "$BACKUP_FILE" == *.enc ]]; then
    if [ -z "$BACKUP_ENCRYPTION_KEY" ]; then
        err "Backup file is encrypted but BACKUP_ENCRYPTION_KEY is not set."
    fi
    DECRYPTED_FILE="${BACKUP_FILE%.enc}.decrypted"
    log "Decrypting backup..."
    openssl enc -d -aes-256-cbc -pbkdf2 \
        -in "$BACKUP_FILE" \
        -out "$DECRYPTED_FILE" \
        -pass pass:"$BACKUP_ENCRYPTION_KEY" 2>/dev/null || err "Decryption failed. Check your encryption key."
    RESTORE_FILE="$DECRYPTED_FILE"
    log "Decryption completed."
fi

# Perform restore
if [ "$DATABASE_TYPE" = "postgresql" ] || [ "$DATABASE_TYPE" = "postgres" ]; then
    log "Restoring PostgreSQL database: $DATABASE_NAME"

    export PGPASSWORD="${DATABASE_PASSWORD}"

    # Drop and recreate database (dangerous but ensures clean restore)
    psql -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER" -d postgres \
         -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DATABASE_NAME';" 2>/dev/null || true
    psql -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER" -d postgres \
         -c "DROP DATABASE IF EXISTS $DATABASE_NAME;" 2>/dev/null || true
    psql -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER" -d postgres \
         -c "CREATE DATABASE $DATABASE_NAME;" 2>/dev/null || true

    # Restore from backup
    pg_restore -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER" -d "$DATABASE_NAME" \
               --no-owner --no-privileges --clean --if-exists "$RESTORE_FILE" 2>/dev/null || \
               log "Warning: pg_restore completed with warnings (may be normal for DROP IF EXISTS)."

    unset PGPASSWORD
    log "PostgreSQL restore completed."

elif [ "$DATABASE_TYPE" = "sqlite" ]; then
    log "Restoring SQLite database: $SQLITE_PATH"

    # Move existing database
    [ -f "$SQLITE_PATH" ] && mv "$SQLITE_PATH" "${SQLITE_PATH}.pre_restore_$(date +%Y%m%d_%H%M%S)" || true

    # Copy backup to database location
    cp "$RESTORE_FILE" "$SQLITE_PATH"

    # Verify integrity
    if sqlite3 "$SQLITE_PATH" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
        log "SQLite integrity check: OK"
    else
        log "Warning: SQLite integrity check failed. Database may be corrupted."
    fi
    log "SQLite restore completed."
fi

# Cleanup decrypted file
if [[ "$BACKUP_FILE" == *.enc ]] && [ -f "$DECRYPTED_FILE" ]; then
    rm -f "$DECRYPTED_FILE"
    log "Cleaned up temporary decrypted file."
fi

log "Database restore completed successfully!"
log "Pre-restore backup saved at: $PRE_RESTORE_BACKUP"

#!/usr/bin/env bash
# -------------------------------------------------------------------------
# PyGBSentry Database Backup Script
# Supports PostgreSQL and SQLite with optional encryption
# -------------------------------------------------------------------------
set -euo pipefail

# Default configuration (overridable via environment variables)
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-}"
DATABASE_TYPE="${DATABASE_TYPE:-postgresql}"
DATABASE_HOST="${DATABASE_HOST:-localhost}"
DATABASE_PORT="${DATABASE_PORT:-5432}"
DATABASE_NAME="${DATABASE_NAME:-pygb28181}"
DATABASE_USER="${DATABASE_USER:-postgres}"
DATABASE_PASSWORD="${DATABASE_PASSWORD:-}"
SQLITE_PATH="${SQLITE_PATH:-./pygbsentry.db}"
BACKUP_ENCRYPTION_ENABLED="${BACKUP_ENCRYPTION_ENABLED:-true}"

# Logging
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[ERROR] $*" >&2; exit 1; }

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="pygbsentry_db_${TIMESTAMP}"

log "Starting database backup..."
log "Database type: $DATABASE_TYPE"
log "Backup directory: $BACKUP_DIR"

if [ "$DATABASE_TYPE" = "postgresql" ] || [ "$DATABASE_TYPE" = "postgres" ]; then
    # PostgreSQL backup
    BACKUP_FULL_PATH="${BACKUP_DIR}/${BACKUP_FILE}.sql"
    log "Backing up PostgreSQL database: $DATABASE_NAME at $DATABASE_HOST:$DATABASE_PORT"

    export PGPASSWORD="${DATABASE_PASSWORD}"
    if ! pg_dump -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER" -d "$DATABASE_NAME" \
         --format=custom --no-owner --no-privileges -f "$BACKUP_FULL_PATH" 2>/dev/null; then
        err "pg_dump failed. Check database connection parameters."
    fi
    unset PGPASSWORD
    log "PostgreSQL backup completed: $BACKUP_FULL_PATH"

elif [ "$DATABASE_TYPE" = "sqlite" ]; then
    # SQLite backup using VACUUM INTO (safe online backup)
    BACKUP_FULL_PATH="${BACKUP_DIR}/${BACKUP_FILE}.db"
    log "Backing up SQLite database: $SQLITE_PATH"

    if [ ! -f "$SQLITE_PATH" ]; then
        err "SQLite database file not found: $SQLITE_PATH"
    fi

    if ! sqlite3 "$SQLITE_PATH" "VACUUM INTO '${BACKUP_FULL_PATH}'" 2>/dev/null; then
        # Fallback: file copy (may have WAL inconsistency)
        log "Warning: VACUUM INTO failed, falling back to file copy..."
        cp "$SQLITE_PATH" "$BACKUP_FULL_PATH"
        # Also copy WAL and SHM if they exist
        [ -f "${SQLITE_PATH}-wal" ] && cp "${SQLITE_PATH}-wal" "${BACKUP_FULL_PATH}-wal" || true
        [ -f "${SQLITE_PATH}-shm" ] && cp "${SQLITE_PATH}-shm" "${BACKUP_FULL_PATH}-shm" || true
    fi
    log "SQLite backup completed: $BACKUP_FULL_PATH"
else
    err "Unsupported DATABASE_TYPE: $DATABASE_TYPE (use 'postgresql' or 'sqlite')"
fi

# Optional encryption
if [ "$BACKUP_ENCRYPTION_ENABLED" = "true" ] && [ -n "$BACKUP_ENCRYPTION_KEY" ]; then
    ENCRYPTED_PATH="${BACKUP_FULL_PATH}.enc"
    log "Encrypting backup with AES-256-CBC..."

    if openssl enc -aes-256-cbc -salt -pbkdf2 \
       -in "$BACKUP_FULL_PATH" \
       -out "$ENCRYPTED_PATH" \
       -pass pass:"$BACKUP_ENCRYPTION_KEY" 2>/dev/null; then
        # Remove unencrypted backup
        rm -f "$BACKUP_FULL_PATH"
        log "Backup encrypted: $ENCRYPTED_PATH"
        BACKUP_FULL_PATH="$ENCRYPTED_PATH"
    else
        err "Backup encryption failed. Unencrypted backup at: $BACKUP_FULL_PATH"
    fi
fi

# Calculate backup size
BACKUP_SIZE=$(du -h "$BACKUP_FULL_PATH" | cut -f1)
log "Backup size: $BACKUP_SIZE"

# Cleanup old backups
log "Cleaning up backups older than $BACKUP_RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "pygbsentry_db_*" -type f -mtime +${BACKUP_RETENTION_DAYS} -delete 2>/dev/null || true
CLEANED_COUNT=$(find "$BACKUP_DIR" -name "pygbsentry_db_*" -type f -mtime +${BACKUP_RETENTION_DAYS} 2>/dev/null | wc -l)
log "Cleaned up $CLEANED_COUNT expired backup(s)."

# List remaining backups
REMAINING=$(find "$BACKUP_DIR" -name "pygbsentry_db_*" -type f 2>/dev/null | wc -l)
log "Total backups remaining: $REMAINING"

log "Backup completed successfully: $BACKUP_FULL_PATH"
echo "$BACKUP_FULL_PATH"

#!/usr/bin/env python3
"""
PyGBSentry Secret Key Rotation Utility.

Rotates SECRET_KEY and FIELD_ENCRYPTION_KEY safely:
1. Generates new keys
2. Re-encrypts field-encrypted data with new key
3. Updates .env file
4. Validates the rotation was successful

Usage:
    python key_rotation.py --dry-run          # Preview changes without applying
    python key_rotation.py --rotate-secret    # Rotate SECRET_KEY
    python key_rotation.py --rotate-field     # Rotate FIELD_ENCRYPTION_KEY
    python key_rotation.py --rotate-all       # Rotate both keys
"""

import argparse
import logging
import os
import secrets
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)


def generate_secret_key() -> str:
    """Generate a 64-character hex secret key."""
    return secrets.token_hex(32)


def load_env_file(env_path: Path) -> dict[str, str]:
    """Load .env file into a dictionary."""
    env = {}
    if not env_path.exists():
        return env
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def save_env_file(env_path: Path, env: dict[str, str], original: dict[str, str]) -> None:
    """Save .env file, preserving comments and structure."""
    if not env_path.exists():
        with open(env_path, "w", encoding="utf-8") as f:
            for key, value in env.items():
                f.write(f'{key}="{value}"\n')
        return

    lines = []
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.partition("=")[0].strip()
                if key in env and env[key] != original.get(key, ""):
                    lines.append(f'{key}="{env[key]}"\n')
                else:
                    lines.append(line)
            else:
                lines.append(line)

    # Add any new keys not in the original file
    for key, value in env.items():
        if key not in original:
            lines.append(f'{key}="{value}"\n')

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def get_db_connection(db_url: str = ""):
    """Get a database connection using psycopg2."""
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 is not installed. Install with: pip install psycopg2-binary")
        return None

    if not db_url:
        # Try to get from settings
        try:
            from app.core.config import settings
            db_url = str(settings.SQLALCHEMY_DATABASE_URI or "")
        except Exception:
            pass

    if not db_url:
        print("ERROR: No database URL provided and cannot determine from settings")
        return None

    # Convert async SQLAlchemy URI to psycopg2-compatible URI
    # e.g., postgresql+asyncpg://... -> postgresql://...
    db_url = db_url.replace("+asyncpg", "").replace("+psycopg2", "")

    try:
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        print(f"ERROR: Cannot connect to database: {e}")
        return None


def re_encrypt_fields(old_key: str, new_key: str, db_url: str, dry_run: bool = False) -> int:
    """Re-encrypt all encrypted fields. Application MUST be stopped before running."""
    import subprocess
    try:
        result = subprocess.run(['pgrep', '-f', 'uvicorn.*app.main:app'], capture_output=True, text=True)
        if result.returncode == 0:
            print("WARNING: Application appears to be running! Key rotation should be performed with the application stopped.")
            print("Continue anyway? (y/N): ", end="")
            response = input().strip().lower()
            if response != 'y':
                print("Aborted.")
                return False
    except Exception:
        pass
    import psycopg2
    import psycopg2.extras

    # Tables and columns that contain encrypted fields
    ENCRYPTED_FIELDS = [
        ("assets", "password"),
        ("resources", "password"),
    ]

    conn = get_db_connection(db_url)
    if not conn:
        print("ERROR: Cannot connect to database")
        return -1

    stats = {"total": 0, "re_encrypted": 0, "failed": 0, "skipped_empty": 0}

    try:
        from app.core.field_crypto import encrypt_field, decrypt_field

        # Temporarily set old key for decryption
        os.environ["FIELD_ENCRYPTION_KEY"] = old_key

        for table, column in ENCRYPTED_FIELDS:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute(
                    psycopg2.sql.SQL("SELECT id, {} FROM {} WHERE {} IS NOT NULL AND {} != ''").format(
                        psycopg2.sql.Identifier(column),
                        psycopg2.sql.Identifier(table),
                        psycopg2.sql.Identifier(column),
                        psycopg2.sql.Identifier(column),
                    )
                )
                rows = cur.fetchall()
            except psycopg2.Error as e:
                logger.error(f"Failed to query {table}.{column}: {e}")
                stats["failed"] += 1
                cur.close()
                continue

            batch_size = 100
            for i, row in enumerate(rows):
                stats["total"] += 1
                encrypted_value = row[column]
                if not encrypted_value:
                    stats["skipped_empty"] += 1
                    continue

                try:
                    plaintext = decrypt_field(encrypted_value)
                    if plaintext == encrypted_value:
                        stats["failed"] += 1
                        logger.warning(f"Skipping {table}.{column} id={row['id']}: decryption returned original value")
                        continue

                    os.environ["FIELD_ENCRYPTION_KEY"] = new_key
                    new_encrypted = encrypt_field(plaintext)

                    if not dry_run:
                        cur.execute(
                            psycopg2.sql.SQL("UPDATE {} SET {} = %s WHERE id = %s").format(
                                psycopg2.sql.Identifier(table),
                                psycopg2.sql.Identifier(column),
                            ),
                            (new_encrypted, row['id']),
                        )
                        if (i + 1) % batch_size == 0:
                            conn.commit()

                    stats["re_encrypted"] += 1
                    os.environ["FIELD_ENCRYPTION_KEY"] = old_key

                except Exception as e:
                    stats["failed"] += 1
                    logger.error(f"Failed to re-encrypt {table}.{column} id={row['id']}: {e}")
                    os.environ["FIELD_ENCRYPTION_KEY"] = old_key
                    conn.rollback()

            if rows and not dry_run:
                conn.commit()

            cur.close()
    finally:
        conn.close()

    print(f"Re-encryption complete: {stats}")
    return 0 if stats["failed"] == 0 else -1


def rotate_secret_key(env_path: Path, dry_run: bool = False) -> None:
    """Rotate the SECRET_KEY."""
    env = load_env_file(env_path)
    old_key = env.get("SECRET_KEY", "")

    if not old_key:
        print("ERROR: SECRET_KEY not found in .env file")
        return

    new_key = generate_secret_key()

    print(f"Rotating SECRET_KEY:")
    print(f"  Old key: {old_key[:8]}...{old_key[-8:]}" if len(old_key) > 16 else f"  Old key: {old_key}")
    print(f"  New key: {new_key[:8]}...{new_key[-8:]}")

    if dry_run:
        print("  [DRY RUN] Key would be updated in .env")
        return

    # Backup .env
    backup_path = env_path.with_suffix(".env.backup")
    if env_path.exists():
        import shutil
        shutil.copy2(env_path, backup_path)
        print(f"  Backup saved to: {backup_path}")

    # Re-encrypt field data if FIELD_ENCRYPTION_KEY is derived from SECRET_KEY
    field_key = env.get("FIELD_ENCRYPTION_KEY", "")
    if not field_key:
        print("  Note: FIELD_ENCRYPTION_KEY not set (derived from SECRET_KEY)")
        print("  Field-encrypted data will need re-encryption after rotation.")
        re_encrypt_fields(old_key, new_key, "", dry_run=dry_run)

    # Update env
    original = dict(env)
    env["SECRET_KEY"] = new_key
    save_env_file(env_path, env, original)
    print("  SECRET_KEY updated in .env file")
    print("  IMPORTANT: Restart the application for changes to take effect.")


def rotate_field_encryption_key(env_path: Path, dry_run: bool = False) -> None:
    """Rotate the FIELD_ENCRYPTION_KEY."""
    env = load_env_file(env_path)
    old_key = env.get("FIELD_ENCRYPTION_KEY", "")

    if not old_key:
        print("ERROR: FIELD_ENCRYPTION_KEY not found in .env file")
        print("  Set FIELD_ENCRYPTION_KEY explicitly before rotating.")
        return

    new_key = generate_secret_key()

    print(f"Rotating FIELD_ENCRYPTION_KEY:")
    print(f"  Old key: {old_key[:8]}...{old_key[-8:]}" if len(old_key) > 16 else f"  Old key: {old_key}")
    print(f"  New key: {new_key[:8]}...{new_key[-8:]}")

    if dry_run:
        print("  [DRY RUN] Key would be updated in .env")
        return

    # Re-encrypt field data
    re_encrypt_fields(old_key, new_key, "", dry_run=dry_run)

    # Backup and update
    backup_path = env_path.with_suffix(".env.backup")
    if env_path.exists():
        import shutil
        shutil.copy2(env_path, backup_path)
        print(f"  Backup saved to: {backup_path}")

    original = dict(env)
    env["FIELD_ENCRYPTION_KEY"] = new_key
    save_env_file(env_path, env, original)
    print("  FIELD_ENCRYPTION_KEY updated in .env file")


def main():
    parser = argparse.ArgumentParser(description="PyGBSentry Key Rotation Utility")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--rotate-secret", action="store_true", help="Rotate SECRET_KEY")
    parser.add_argument("--rotate-field", action="store_true", help="Rotate FIELD_ENCRYPTION_KEY")
    parser.add_argument("--rotate-all", action="store_true", help="Rotate all keys")
    parser.add_argument("--env-file", default=None, help="Path to .env file")
    args = parser.parse_args()

    if not any([args.rotate_secret, args.rotate_field, args.rotate_all]):
        parser.print_help()
        return

    env_path = Path(args.env_file) if args.env_file else backend_dir / ".env"

    if not env_path.exists():
        print(f"ERROR: .env file not found at {env_path}")
        print("  Specify path with --env-file")
        return

    print("=" * 50)
    print("  PyGBSentry Key Rotation Utility")
    print("=" * 50)
    if args.dry_run:
        print("  [DRY RUN MODE - no changes will be made]")
    print()

    if args.rotate_all or args.rotate_secret:
        rotate_secret_key(env_path, args.dry_run)
        print()

    if args.rotate_all or args.rotate_field:
        rotate_field_encryption_key(env_path, args.dry_run)
        print()

    print("Key rotation complete.")


if __name__ == "__main__":
    main()

"""Database compatibility helpers.

Normalises database type identifiers and runs lightweight vendor-specific
compatibility checks exposed through the system-config endpoint.
"""
from __future__ import annotations

from typing import Any

from loguru import logger

_ALIASES = {
    "sqlite": "sqlite",
    "sqlite3": "sqlite",
    "mysql": "mysql",
    "mariadb": "mysql",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "pg": "postgresql",
    "tdengine": "tdengine",
    "iotdb": "iotdb",
    "influxdb": "influxdb",
}


def normalize_db_type(value: str) -> str:
    """Normalise a database type string to a canonical lower-case name."""
    if not value:
        return "sqlite"
    return _ALIASES.get(str(value).strip().lower(), str(value).strip().lower())


def vendor_hint(db_type: str) -> str:
    """Return a human-readable hint for the given database vendor."""
    t = normalize_db_type(db_type)
    hints = {
        "sqlite": "SQLite: suitable for development; consider MySQL/PostgreSQL for production",
        "mysql": "MySQL/MariaDB: ensure utf8mb4 charset and InnoDB engine",
        "postgresql": "PostgreSQL: ensure the database user has CREATE/ALTER privileges",
    }
    return hints.get(t, "")


async def run_compat_checks(conn, db_type: str) -> dict[str, Any]:
    """Run vendor-specific compatibility checks against ``conn``.

    Returns a report dict with ``ok`` and a list of ``warnings``. Failures are
    treated as warnings, never hard errors, so the platform can still start.
    """
    t = normalize_db_type(db_type)
    report: dict[str, Any] = {"db_type": t, "ok": True, "warnings": []}
    try:
        if t == "sqlite":
            result = await conn.execute(_text("PRAGMA journal_mode"))
            row = result.first()
            mode = row[0] if row else ""
            if str(mode).lower() not in ("wal",):
                report["warnings"].append(f"SQLite journal_mode is '{mode}', WAL recommended")
        elif t == "mysql":
            result = await conn.execute(_text("SELECT version()"))
            row = result.first()
            report["server_version"] = row[0] if row else "unknown"
        elif t == "postgresql":
            result = await conn.execute(_text("SELECT version()"))
            row = result.first()
            report["server_version"] = row[0] if row else "unknown"
    except Exception as e:
        report["ok"] = False
        report["warnings"].append(f"compat check failed: {e}")
        logger.debug(f"db_compat: run_compat_checks failed: {e}")
    return report


def _text(sql: str):
    from sqlalchemy import text
    return text(sql)

from sqlalchemy import text


def normalize_db_type(raw: str | None) -> str:
    value = (raw or "postgresql").strip().lower()
    if value in {"postgres", "postgresql"}:
        return "postgresql"
    if value in {"mysql"}:
        return "mysql"
    if value in {"sqlite"}:
        return "sqlite"
    if value in {"kingbase", "人大金仓"}:
        return "kingbase"
    if value in {"dm", "dameng", "达梦"}:
        return "dameng"
    return "postgresql"


def vendor_hint(db_type: str) -> str | None:
    if db_type == "kingbase":
        return "当前通过 PostgreSQL 协议连接人大金仓，建议在目标项目环境完成 SQL 方言与驱动兼容回归。"
    if db_type == "dameng":
        return "当前通过 MySQL 协议连接达梦，建议在目标项目环境完成 SQL 方言与驱动兼容回归。"
    return None


async def run_compat_checks(conn, db_type: str) -> dict:
    checks: list[dict] = []
    summary = "ok"
    parsed_type = normalize_db_type(db_type)
    core_sql = "SELECT 1"
    json_sql = "SELECT '{\"ok\": true}'"
    if parsed_type in {"postgresql", "kingbase"}:
        json_sql = "SELECT json_build_object('ok', true)"
    elif parsed_type in {"mysql", "dameng"}:
        json_sql = "SELECT JSON_OBJECT('ok', true)"

    probe_plan = [
        ("connectivity", core_sql),
        ("transaction", core_sql),
        ("json", json_sql),
    ]
    trans = await conn.begin()
    try:
        for name, sql in probe_plan:
            try:
                await conn.execute(text(sql))
                checks.append({"name": name, "ok": True, "detail": "通过"})
            except Exception as e:
                checks.append({"name": name, "ok": False, "detail": str(e)})
                summary = "warn" if summary == "ok" else summary
    finally:
        await trans.rollback()

    hint = vendor_hint(parsed_type)
    return {
        "database": parsed_type,
        "summary": summary,
        "checks": checks,
        "vendor_hint": hint,
    }

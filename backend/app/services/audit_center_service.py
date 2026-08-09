import uuid
from datetime import datetime, timezone
try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def _uuid7_hex(n: int = 16) -> str:
    return _uuid7_impl().hex[:n]

from sqlalchemy import select, desc, and_, or_, func  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.operation_audit import OperationAudit
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务
from loguru import logger




class AuditCenterService:
    async def _push_to_external_siem(self, payload: dict) -> None:  # W-05 改为async，使用httpx异步请求替代同步requests.post
        """
        M6-02: 审计日志外部对接支持（Webhook / Syslog 实时推送至 SIEM/态势感知）
        读取配置并推送日志
        """
        from app.core.config import settings
        webhook_url = settings.AUDIT_WEBHOOK_URL
        webhook_timeout = settings.AUDIT_WEBHOOK_TIMEOUT
        if webhook_url:
            try:
                # FIX: [2026-07-04] 使用进程级共享 HTTP 客户端，避免每次调用创建/销毁 AsyncClient 导致连接池泄漏 [可靠性工程师]
                from app.core.http_client import get_http_client
                client = await get_http_client()
                await client.post(webhook_url, json=payload, timeout=float(webhook_timeout))
            except Exception as e:
                logger.error(f"Failed to push audit log to SIEM webhook: {e}")

    def _summary_kv(self, summary: str | None) -> dict[str, str]:
        """
        Best-effort parsing for `key=value; key2=value2` summary strings.
        We keep it permissive so older/partial formats won't break list APIs.
        """
        if not summary:
            return {}
        out: dict[str, str] = {}
        for part in summary.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k and v != "":
                out[k] = v
        return out
    def _summary_field_condition(self, key: str, value: str):
        token = f"{key}={value}"
        return or_(
            OperationAudit.summary == token,
            OperationAudit.summary.like(f"{token}; %"),
            # token 后面带空格或不带空格分隔符：兼容 summary 拼接格式差异
            OperationAudit.summary.like(f"{token};%"),
            OperationAudit.summary.like(f"%; {token}; %"),
            OperationAudit.summary.like(f"%; {token};%"),
            OperationAudit.summary.like(f"%;{token}; %"),
            OperationAudit.summary.like(f"%;{token};%"),
            OperationAudit.summary.like(f"%; {token}"),
            OperationAudit.summary.like(f"%;{token}"),
        )

    def _to_iso(self, dt: datetime | None) -> str:
        if not dt:
            return datetime.now(timezone.utc).isoformat()
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc).isoformat()
        return dt.astimezone(timezone.utc).isoformat()

    def _apply_summary_filters(
        self,
        stmt,
        *,
        plugin_id: str | None = None,
        source: str | None = None,
        tenant_id: str | None = None,
        status_code: int | None = None,
        status_family: int | None = None,
    ):
        fixed_conditions = []
        if plugin_id:
            fixed_conditions.append(self._summary_field_condition("plugin_id", plugin_id))
        if source:
            fixed_conditions.append(self._summary_field_condition("source", source))
        if tenant_id:
            # FIX: [2026-07-04] 原仅通过 summary 文本匹配 tenant_id=xxx，但 safe_auth_audit 将 tenant_id 写入
            # OperationAudit.tenant_id 专列而非 summary 文本，导致租户级审计日志隔离完全失效 [全栈工程师]
            # 修正：优先使用专列查询，兼容 summary 文本中包含 tenant_id 的旧记录
            fixed_conditions.append(or_(
                OperationAudit.tenant_id == tenant_id,
                self._summary_field_condition("tenant_id", tenant_id),
            ))
        if status_code is not None:
            fixed_conditions.append(self._summary_field_condition("status_code", str(status_code)))

        status_family_conditions = []
        if status_family is not None:
            for code in range(status_family * 100, status_family * 100 + 100):
                status_family_conditions.append(self._summary_field_condition("status_code", str(code)))

        if fixed_conditions:
            stmt = stmt.where(and_(*fixed_conditions))
        if status_family_conditions:
            stmt = stmt.where(or_(*status_family_conditions))
        return stmt

    def _build_filtered_stmt(
        self,
        *,
        module: str | None = None,
        action: str | None = None,
        action_prefix: str | None = None,
        operator: str | None = None,
        result: str | None = None,
        plugin_id: str | None = None,
        source: str | None = None,
        tenant_id: str | None = None,
        status_code: int | None = None,
        status_family: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ):
        stmt = select(OperationAudit)
        if module:
            stmt = stmt.where(OperationAudit.module == module)
        if action:
            stmt = stmt.where(OperationAudit.action == action)
        if action_prefix:
            stmt = stmt.where(OperationAudit.action.like(f"{action_prefix}%"))
        if operator:
            stmt = stmt.where(OperationAudit.operator == operator)
        if result:
            stmt = stmt.where(OperationAudit.result == result)
        stmt = self._apply_summary_filters(
            stmt,
            plugin_id=plugin_id,
            source=source,
            tenant_id=tenant_id,
            status_code=status_code,
            status_family=status_family,
        )
        if start_at:
            stmt = stmt.where(OperationAudit.created_at >= start_at)
        if end_at:
            stmt = stmt.where(OperationAudit.created_at <= end_at)
        return stmt

    async def log(
        self,
        db: AsyncSession,
        module: str,
        action: str,
        operator: str,
        result: str,
        summary: str,
    ) -> dict:
        audit_id = _uuid7_hex(12)
        row = OperationAudit(
            id=audit_id,
            module=module,
            action=action,
            operator=operator or "unknown",
            result=result,
            summary=summary,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        payload = {
            "audit_id": f"au_{row.id}",
            "module": row.module,
            "action": row.action,
            "operator": row.operator,
            "result": row.result,
            "summary": row.summary,
            "created_at": self._to_iso(row.created_at),
        }

        # 异步推送至态势感知/SIEM
        try:
            fire_and_forget(self._push_to_external_siem(payload))  # P0-16: 保存引用防 GC + 异常日志
        except Exception as e:
            logger.warning(f"Error: {e}")

        return payload

    async def list_logs(
        self,
        db: AsyncSession,
        module: str | None = None,
        action: str | None = None,
        action_prefix: str | None = None,
        operator: str | None = None,
        result: str | None = None,
        plugin_id: str | None = None,
        source: str | None = None,
        tenant_id: str | None = None,
        status_code: int | None = None,
        status_family: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        base_stmt = self._build_filtered_stmt(
            module=module,
            action=action,
            action_prefix=action_prefix,
            operator=operator,
            result=result,
            plugin_id=plugin_id,
            source=source,
            tenant_id=tenant_id,
            status_code=status_code,
            status_family=status_family,
            start_at=start_at,
            end_at=end_at,
        )
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = int(total_result.scalar() or 0)
        safe_page = max(page, 1)
        safe_page_size = max(min(page_size, 200), 1)
        begin = (safe_page - 1) * safe_page_size
        stmt = base_stmt.order_by(desc(OperationAudit.created_at)).offset(begin).limit(safe_page_size)
        result_set = await db.execute(stmt)
        paged = result_set.scalars().all()
        items = []
        for row in paged:
            kv = self._summary_kv(row.summary)
            status_code_raw = kv.get("status_code") or ""
            status_code_val = int(status_code_raw) if status_code_raw.isdigit() else None
            items.append(
                {
                    "audit_id": f"au_{row.id}",
                    "module": row.module,
                    "action": row.action,
                    "operator": row.operator,
                    "result": row.result,
                    "summary": row.summary,
                    "plugin_id": kv.get("plugin_id"),
                    "source": kv.get("source"),
                    "tenant_id": kv.get("tenant_id"),
                    "status_code": status_code_val,
                    "created_at": self._to_iso(row.created_at),
                }
            )
        return {"total": total, "items": items}

    async def export_csv(
        self,
        db: AsyncSession,
        module: str | None = None,
        action: str | None = None,
        action_prefix: str | None = None,
        operator: str | None = None,
        result: str | None = None,
        plugin_id: str | None = None,
        source: str | None = None,
        tenant_id: str | None = None,
        status_code: int | None = None,
        status_family: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        max_rows: int = 10000,
    ) -> str:
        """Export audit logs as CSV (same filters as list_logs)."""
        stmt = self._build_filtered_stmt(
            module=module,
            action=action,
            action_prefix=action_prefix,
            operator=operator,
            result=result,
            plugin_id=plugin_id,
            source=source,
            tenant_id=tenant_id,
            status_code=status_code,
            status_family=status_family,
            start_at=start_at,
            end_at=end_at,
        ).order_by(desc(OperationAudit.created_at)).limit(max_rows)
        result_set = await db.execute(stmt)
        rows = result_set.scalars().all()
        lines = ["\ufeff时间,模块,动作,操作人,结果,插件ID,来源,租户,状态码,摘要"]
        for row in rows:
            kv = self._summary_kv(row.summary)
            plugin_id_val = (kv.get("plugin_id") or "").replace('"', '""')
            source_val = (kv.get("source") or "").replace('"', '""')
            tenant_val = (kv.get("tenant_id") or "").replace('"', '""')
            status_code_val = (kv.get("status_code") or "").replace('"', '""')
            created = self._to_iso(row.created_at) if row.created_at else ""
            summary_esc = (row.summary or "").replace('"', '""')
            lines.append(
                f'"{created}","{row.module or ""}","{row.action or ""}","{row.operator or ""}","{row.result or ""}",'
                f'"{plugin_id_val}","{source_val}","{tenant_val}","{status_code_val}","{summary_esc}"'
            )
        return "\n".join(lines)

    async def get_stats(
        self,
        db: AsyncSession,
        module: str | None = None,
        action: str | None = None,
        action_prefix: str | None = None,
        operator: str | None = None,
        result: str | None = None,
        plugin_id: str | None = None,
        source: str | None = None,
        tenant_id: str | None = None,
        status_code: int | None = None,
        status_family: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> dict:
        # FIX: [2026-07-16 P0-C] 原实现加载所有审计日志到内存后 Python 聚合，
        # 180天保留期 + 百万级记录 = OOM。改用 SQL 聚合 + 有限行扫描。
        base_stmt = self._build_filtered_stmt(
            module=module,
            action=action,
            action_prefix=action_prefix,
            operator=operator,
            result=result,
            plugin_id=plugin_id,
            source=source,
            tenant_id=tenant_id,
            status_code=status_code,
            status_family=status_family,
            start_at=start_at,
            end_at=end_at,
        )
        # 移除 order_by 以优化聚合查询
        base_stmt_no_order = base_stmt.order_by(None)

        # 1. 总数（SQL COUNT）
        total_stmt = base_stmt_no_order.with_only_columns(func.count())
        total = int((await db.execute(total_stmt)).scalar() or 0)

        # 2. 失败数（SQL COUNT WHERE result='failed'）
        failed_stmt = base_stmt_no_order.where(
            OperationAudit.result == "failed"
        ).with_only_columns(func.count())
        failed = int((await db.execute(failed_stmt)).scalar() or 0)

        # 3. Top 5 动作（SQL GROUP BY）
        actions_stmt = base_stmt_no_order.with_only_columns(
            OperationAudit.action, func.count().label("cnt")
        ).group_by(OperationAudit.action).order_by(desc("cnt")).limit(5)
        actions_result = await db.execute(actions_stmt)
        top_actions = [
            {"name": row[0] or "-", "count": row[1]}
            for row in actions_result.all()
        ]

        # 4. 状态码统计：status_code 存储在 summary 文本中，无法用 SQL 高效聚合。
        # 仅扫描最近 N 条记录进行解析，避免全表加载导致 OOM。
        _status_scan_limit = 10000
        status_stmt = base_stmt.order_by(
            desc(OperationAudit.created_at)
        ).limit(_status_scan_limit)
        status_result = await db.execute(status_stmt)
        status_rows = status_result.scalars().all()
        status_count: dict[str, int] = {}
        status_buckets: dict[str, int] = {"401": 0, "402": 0, "403": 0, "409": 0, "5xx": 0}
        for row in status_rows:
            summary = str(row.summary or "")
            for token in [x.strip() for x in summary.split(";") if x.strip()]:
                if token.startswith("status_code="):
                    code = token.split("=", 1)[1].strip()
                    if code:
                        status_count[code] = status_count.get(code, 0) + 1
                        if code in status_buckets:
                            status_buckets[code] += 1
                        try:
                            code_num = int(code)
                            if 500 <= code_num <= 599:
                                status_buckets["5xx"] += 1
                        except Exception as _code_err:
                            # FIX [2026-07-17 P3-30]: 描述性日志替代静默吞异常
                            logger.debug(f"audit_center: failed to parse status code '{code}' for 5xx bucketing: {_code_err}")
                    break
        top_status_codes = sorted(status_count.items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "total": total,
            "failed": failed,
            "top_actions": top_actions,
            "top_status_codes": [{"code": k, "count": v} for k, v in top_status_codes],
            "status_buckets": status_buckets,
        }


audit_center_service = AuditCenterService()

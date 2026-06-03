"""
授权并集计算引擎（开源版）

计算租户的插件授权并集 = {单品已购} ∪ {套餐内含}

开源版采用 AsyncSession，与 server 版的 sync Session 版本互补。

调用方：plugin_manager.py:_compute_eligible_plugin_ids()
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Set, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    TenantSubscription,
    BillingPlan,
    PluginOrder,
)


def _parse_plugin_entitlements(raw: Optional[str]) -> Set[str]:
    """
    解析 plugin_entitlements 字段。
    支持两种格式：
    1. JSON 数组: ["plugin_a", "plugin_b"]
    2. 逗号分隔字符串: "plugin_a,plugin_b"
    """
    if not raw:
        return set()
    raw = str(raw).strip()
    if not raw:
        return set()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return {str(x).strip() for x in parsed if x}
        return set()
    except (json.JSONDecodeError, TypeError):
        return {s.strip() for s in raw.split(",") if s.strip()}


class EntitlementEngine:
    """
    授权并集计算引擎。

    核心公式: eligible = {单品已购} ∪ {套餐内含}

    开放接口供 plugin_manager 等核心模块调用。
    """

    @staticmethod
    async def compute_eligible_plugins(db: AsyncSession, tenant_id: str) -> Set[str]:
        """
        计算租户的有效插件 ID 并集。

        规则：
        1. {单品已购}: PluginOrder.status=="paid" 且未过期（含永久授权 perpetual）
        2. {套餐内含}: TenantSubscription.status=="active" 且未过期，对应 BillingPlan.plugin_entitlements

        Args:
            db: AsyncSession 数据库会话
            tenant_id: 租户 ID

        Returns:
            Set[str]: 该租户可用的插件 ID 集合，永不返回 None
        """
        tid = str(tenant_id).strip() if tenant_id else ""
        if not tid:
            logger.warning("EntitlementEngine.compute_eligible_plugins: empty tenant_id, returning empty set")
            return set()

        now = datetime.now(timezone.utc)  # datetime.utcnow() 已弃用(Python 3.12+) → datetime.now(timezone.utc)
        single_paid: Set[str] = set()
        plan_entitled: Set[str] = set()

        try:
            # ---- ① 单品已购 (PluginOrder) ----
            order_stmt = select(PluginOrder).where(
                PluginOrder.tenant_id == tid,
                PluginOrder.status == "paid",
            )
            order_result = await db.execute(order_stmt)
            for order in order_result.scalars().all():
                # 已过期（且非永久授权）
                if order.expires_at and order.expires_at < now:
                    continue
                # 永久授权 或 未过期 或 billing_period=="perpetual"（无过期时间）
                if order.billing_period == "perpetual" or order.expires_at is None or order.expires_at >= now:
                    if order.plugin_id:
                        single_paid.add(str(order.plugin_id).strip())

            # ---- ② 套餐内含 (TenantSubscription -> BillingPlan) ----
            sub_stmt = select(TenantSubscription).where(
                TenantSubscription.tenant_id == tid,
                TenantSubscription.status == "active",
            )
            sub_result = await db.execute(sub_stmt)
            sub = sub_result.scalars().first()
            if sub:
                # 订阅未过期（ends_at 为 None 表示永久有效）
                if sub.ends_at is None or sub.ends_at >= now:
                    if sub.plan_code:
                        plan_stmt = select(BillingPlan).where(BillingPlan.code == sub.plan_code)
                        plan_result = await db.execute(plan_stmt)
                        plan = plan_result.scalars().first()
                        if plan and plan.plugin_entitlements:
                            plan_entitled = _parse_plugin_entitlements(plan.plugin_entitlements)

        except Exception as e:
            logger.error(
                "EntitlementEngine.compute_eligible_plugins: DB query failed for tenant=%s: %s",
                tid, e,
            )
            return set()

        eligible = single_paid | plan_entitled
        logger.debug(
            "EntitlementEngine[async]: tenant=%s | single_paid=%s | plan_entitled=%s | eligible=%s",
            tid, single_paid, plan_entitled, eligible,
        )
        return eligible

    @staticmethod
    async def check_plugin_authorized(db: AsyncSession, tenant_id: str, plugin_id: str) -> bool:
        """
        便捷方法：判断单个插件是否在授权并集中。
        """
        eligible = await EntitlementEngine.compute_eligible_plugins(db, tenant_id)
        pid = str(plugin_id).strip() if plugin_id else ""
        return pid in eligible


class AsyncEntitlementEngine:
    """
    AsyncEntitlementEngine 是 EntitlementEngine 的别名，供习惯 server 版命名风格的调用方使用。

    server 版同时有 sync EntitlementEngine 和 async AsyncEntitlementEngine。
    开源版统一使用 async 接口，保留此别名以保持 API 兼容性。
    """

    @staticmethod
    async def compute_eligible_plugins(db: AsyncSession, tenant_id: str) -> Set[str]:
        return await EntitlementEngine.compute_eligible_plugins(db, tenant_id)

    @staticmethod
    async def check_plugin_authorized(db: AsyncSession, tenant_id: str, plugin_id: str) -> bool:
        return await EntitlementEngine.check_plugin_authorized(db, tenant_id, plugin_id)

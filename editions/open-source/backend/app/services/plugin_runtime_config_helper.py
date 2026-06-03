from __future__ import annotations

import json
from typing import Any
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy import select

from app.models.system_setting import SystemSetting


async def load_plugin_runtime_config(
    db: AsyncSession,
    *,
    plugin_id: str,
    tenant_id: str,
    base_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    读取插件运行时配置（配置中心保存到 system_settings 表）并合并默认 config_template。

    setting_key 约定：
      plugin_runtime_config.{tenant_id}.{plugin_id}
    """
    base = dict(base_config or {})
    setting_key = f"plugin_runtime_config.{(tenant_id or 'default').strip() or 'default'}.{plugin_id}"
    setting = (await db.execute(select(SystemSetting).where(SystemSetting.setting_key == setting_key))).scalars().first()
    if not setting or not setting.setting_value:
        return base
    try:
        saved = json.loads(setting.setting_value)
        if isinstance(saved, dict):
            base.update(saved)
    except Exception as e:
        logger.warning(f"插件运行时配置解析失败: {e}")
    return base


"""SSL 证书管理器（certbot 启动检查与续期）。

在 ``main.py`` lifespan 启动阶段调用 :func:`on_startup` 检查证书状态并按需
启动续期定时器。该模块在 Windows 平台上为 no-op（``platform_supported=False``），
且整体调用被 ``main.py`` 的 ``try/except`` 包裹，不会阻断启动。
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from typing import Optional

from loguru import logger

from app.services.ssl_certbot.certbot_config import CertbotSettings


def _load_settings() -> CertbotSettings:
    """从全局 settings 加载 certbot 配置。"""
    from app.core.config import settings
    return CertbotSettings(
        enabled=bool(getattr(settings, "SSLCERT_ENABLED", False)),
        domain=getattr(settings, "SSLCERT_DOMAIN", "") or "",
        email=getattr(settings, "SSLCERT_EMAIL", "") or "",
        mode=getattr(settings, "SSLCERT_MODE", "webroot") or "webroot",
    )


_renew_task: Optional[asyncio.Task] = None


async def on_startup() -> None:
    """启动检查：验证 certbot 可用性，按需启动续期定时器。

    - Windows 平台：直接跳过（``platform_supported=False``）。
    - ``enabled=False``：跳过。
    - certbot 未安装：记录警告并跳过。
    - 一切就绪：启动周期续期检查任务。
    """
    global _renew_task

    if sys.platform == "win32":
        logger.info("SSL certbot: Windows platform, skipping (platform_supported=False)")
        return

    try:
        cfg = _load_settings()
    except Exception as e:
        logger.warning(f"SSL certbot: failed to load settings, skipping: {e}")
        return

    if not cfg.enabled:
        logger.info("SSL certbot: disabled by config (SSLCERT_ENABLED=false)")
        return

    if not shutil.which("certbot"):
        logger.warning("SSL certbot: certbot binary not found in PATH, skipping")
        return

    logger.info(f"SSL certbot: enabled, domain={cfg.domain}, mode={cfg.mode}")

    # 启动续期检查定时器
    interval_seconds = cfg.renew_check_interval_hours * 3600
    _renew_task = asyncio.create_task(_renew_loop(interval_seconds))


async def on_shutdown() -> None:
    """停止续期定时器。"""
    global _renew_task
    if _renew_task and not _renew_task.done():
        _renew_task.cancel()
        try:
            await asyncio.wait_for(_renew_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.debug("task_cancelled")
    _renew_task = None


async def _renew_loop(interval_seconds: int) -> None:
    """周期检查证书是否需要续期。"""
    logger.info(f"SSL certbot renew loop started: interval={interval_seconds}s")
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "certbot", "renew", "--quiet",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0:
                    logger.info("SSL certbot renew check completed: no action needed")
                else:
                    logger.warning(
                        f"SSL certbot renew failed: exit={proc.returncode} "
                        f"stderr={stderr.decode('utf-8', errors='ignore')[:500]}"
                    )
            except Exception as e:
                logger.warning(f"SSL certbot renew check error: {e}")
    except asyncio.CancelledError:
        logger.info("SSL certbot renew loop cancelled")

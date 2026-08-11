"""SSL 证书管理器（certbot 启动检查与续期）。

在 ``main.py`` lifespan 启动阶段调用 :func:`on_startup` 检查证书状态并按需
启动续期定时器。该模块在 Windows 平台上为 no-op（``platform_supported=False``），
且整体调用被 ``main.py`` 的 ``try/except`` 包裹，不会阻断启动。
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.services.ssl_certbot.certbot_config import CertbotSettings


# FIX: [2026-07-13] 从 2ad636a 恢复 — ssl_cert 端点需要 get_status() 和
# force_renew() 函数，但 ConvergeLoop Round 0 删除了它们，导致
# /api/v1/ssl-cert/* 全部 404。以下是兼容当前代码库的实现。[全栈工程师]

@dataclass
class CertInfo:
    """SSL 证书状态信息（供 ssl_cert 端点使用）。"""
    domain: str = ""
    status: str = "disabled"
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None
    remaining_days: int = 0
    cert_path: str = ""
    last_renew_at: Optional[datetime] = None
    last_check_at: Optional[datetime] = None
    error: str = ""


def _load_settings() -> CertbotSettings:
    """从全局 settings 加载 certbot 配置。"""
    from app.core.config import settings
    return CertbotSettings(
        enabled=settings.SSL_CERTBOT_ENABLED,
        domain=settings.SSL_CERTBOT_DOMAIN or "",
        email=settings.SSL_CERTBOT_EMAIL or "",
        mode=settings.SSL_CERTBOT_MODE or "webroot",
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


# ─── ssl_cert 端点所需的 API 函数 ─────────────────────────────────────────────
# FIX: [2026-07-13] 从 2ad636a 恢复 — ssl_cert 端点导入 get_status 和 force_renew
# 但 ConvergeLoop Round 0 删除了它们。以下实现兼容当前 certbot_manager 架构。
# [全栈工程师]

_last_cert_info: Optional[CertInfo] = None


async def get_status() -> CertInfo:
    """返回当前 SSL 证书状态。

    - Windows 平台：返回 ``unsupported_platform`` 状态。
    - 未启用：返回 ``disabled`` 状态。
    - Linux + 已启用：尝试读取证书文件并返回实际状态。
    """
    global _last_cert_info
    cfg = _load_settings()
    if not cfg.enabled:
        return CertInfo(domain=cfg.domain, status="disabled")

    if sys.platform == "win32":
        return CertInfo(
            domain=cfg.domain,
            status="unsupported_platform",
            error="SSL certbot is not supported on Windows",
        )

    # 尝试通过 cert_checker 检查实际证书状态
    try:
        from app.services.ssl_certbot.cert_checker import check_cert_status
        cert_path = f"/etc/letsencrypt/live/{cfg.domain}/cert.pem"
        info = await check_cert_status(cert_path, cfg.domain)
        _last_cert_info = info
        info.last_check_at = datetime.now(timezone.utc)
        return info
    except Exception as e:
        logger.warning(f"SSL cert status check failed: {e}")
        return CertInfo(domain=cfg.domain, status="error", error=str(e))


async def force_renew() -> tuple[bool, str]:
    """强制续期 SSL 证书。

    Returns:
        ``(success, message)`` 元组。
    """
    cfg = _load_settings()
    if not cfg.enabled:
        return False, "SSL certbot is not enabled"

    if sys.platform == "win32":
        return False, "SSL certbot is not supported on Windows"

    if not shutil.which("certbot"):
        return False, "certbot binary not found in PATH"

    try:
        proc = await asyncio.create_subprocess_exec(
            "certbot", "renew", "--force-renewal",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            global _last_cert_info
            _last_cert_info = await get_status()
            if _last_cert_info:
                _last_cert_info.last_renew_at = datetime.now(timezone.utc)
            return True, "Certificate renewed successfully"
        err_msg = stderr.decode("utf-8", errors="ignore")[:200]
        return False, f"Renewal failed (exit={proc.returncode}): {err_msg}"
    except Exception as e:
        return False, str(e)

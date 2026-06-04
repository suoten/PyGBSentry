from app.db.session import AsyncSessionLocal, engine
from app.db.base import Base
from app.db.model_registry import ensure_model_registry_loaded
from app.models.user import User
from app.models.media_node import MediaNode
from app.models.billing import BillingPlan, TenantSubscription
from app.core import security
from app.core.config import settings
from sqlalchemy import select
import asyncio
import hashlib
import logging
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from loguru import logger

async def init_db():
    # 先注册全部模型，保证 Base.metadata.create_all 能建出 system_settings 等全部表
    ensure_model_registry_loaded()
    # 1. Create tables if they don't exist
    logger.info("Checking database schema...")
    async with engine.begin() as conn:
        # run_sync expects a sync function, so we pass metadata.create_all
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized.")

    # 2. Create default admin user
    async with AsyncSessionLocal() as session:
        # Check if admin exists
        stmt = select(User).where(User.username == "admin")
        result = await session.execute(stmt)
        user = result.scalars().first()

        # 支持通过环境变量 ADMIN_INITIAL_PASSWORD 指定初始密码
        # removed --password= CLI support to prevent password exposure in process list (ps aux)
        # FIXED: 优先从 settings 读取（pydantic-settings 会加载 .env 文件），
        # 回退到 os.environ（支持命令行 ADMIN_INITIAL_PASSWORD=xxx 方式）
        _admin_password = ""
        try:
            from app.core.config import settings as _settings
            _admin_password = getattr(_settings, "ADMIN_INITIAL_PASSWORD", "") or ""
        except Exception:
            pass
        if not _admin_password:
            _admin_password = os.environ.get("ADMIN_INITIAL_PASSWORD", "").strip()

        if not user:
            if not _admin_password:
                _admin_password = secrets.token_urlsafe(12)
            logger.info("Creating default admin user...")
            user = User(
                username="admin",
                hashed_password=security.get_password_hash(_admin_password),
                is_superuser=True,
                is_active=True,
                full_name="Administrator",
                tenant_id="default",
                role="owner"
            )
            session.add(user)
            await session.commit()
            logger.info("Default admin user created.")
            # removed password fingerprint from logs to prevent offline brute-force
            logger.warning("=" * 60)
            logger.warning("IMPORTANT: Admin password has been set.")
            logger.warning("Retrieve the password from ADMIN_INITIAL_PASSWORD env.")
            logger.warning("Please change it immediately after first login!")
            logger.warning("=" * 60)
        else:
            if _admin_password:
                user.hashed_password = security.get_password_hash(_admin_password)
                user.failed_login_attempts = 0
                user.locked_until = None
                user.is_active = True
                user.is_superuser = True
                user.role = "owner"
                await session.commit()
                # removed password fingerprint from logs to prevent offline brute-force
                logger.warning("=" * 60)
                logger.warning("Admin password has been RESET.")
                logger.warning("Account lock has been CLEARED.")
                logger.warning("Please change it immediately after first login!")
                logger.warning("=" * 60)
            else:
                logger.info("Admin user already exists. To reset password, set ADMIN_INITIAL_PASSWORD env or run with --password=YOUR_PASSWORD")
        plan_stmt = select(BillingPlan).where(BillingPlan.code == "community")
        plan_result = await session.execute(plan_stmt)
        community = plan_result.scalars().first()
        if not community:
            community = BillingPlan(
                code="community",
                name="Community",
                price_monthly=0,
                max_devices=0,
                max_channels=0,
                plugin_entitlements="",
                is_active=True,
            )
            session.add(community)
        sub_stmt = select(TenantSubscription).where(TenantSubscription.tenant_id == "default")
        sub_result = await session.execute(sub_stmt)
        default_sub = sub_result.scalars().first()
        if not default_sub:
            enable_trial = False
            trial_days = 0
            try:
                import httpx
                base_url = (settings.PLUGIN_MARKETPLACE_BASE_URL or "").rstrip("/")
                record_url = (getattr(settings, "PLUGIN_SERVER_RECORD_URL", None) or "").strip()
                if record_url:
                    from urllib.parse import urlparse
                    parsed = urlparse(record_url)
                    if parsed.netloc:
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                if base_url:
                    async with httpx.AsyncClient(timeout=5) as client:
                        resp = await client.get(f"{base_url}/api/v1/plugins/trial-config")
                        if resp.status_code == 200:
                            cfg = resp.json()
                            enable_trial = bool(cfg.get("enable_trial", False))
                            trial_days = int(cfg.get("default_trial_days", 7) or 7) if enable_trial else 0
            except Exception as e:
                logger.warning(f"Error: {e}")
            if not enable_trial:
                trial_days = max(0, int(getattr(settings, "TRIAL_DAYS", 7) or 0))
                enable_trial = trial_days > 0
            trial_ends_at = datetime.now(timezone.utc) + timedelta(days=trial_days) if enable_trial and trial_days > 0 else None
            default_sub = TenantSubscription(
                tenant_id="default",
                plan_code="community",
                status="trial" if trial_ends_at else "active",
                trial_ends_at=trial_ends_at,
            )
            session.add(default_sub)
            if trial_ends_at:
                logger.info(f"Default subscription created with {trial_days}-day trial (expires {trial_ends_at.isoformat()})")
            else:
                logger.info("Default subscription created (no trial)")
        await session.commit()

        # 3. Seed default embedded media node (so 运维中心可见且可直接设为活动)
        try:
            mn_result = await session.execute(select(MediaNode).limit(1))
            any_mn = mn_result.scalars().first()
            if not any_mn:
                hook_base = (
                    getattr(settings, "MEDIA_SERVER_HOOK_BASE_URL", None)
                    or f"http://{settings.BACKEND_PUBLIC_HOST}:{settings.BACKEND_PUBLIC_PORT}{settings.API_V1_STR}/hook"
                )
                embedded = MediaNode(
                    ip=str(getattr(settings, "MEDIA_SERVER_HOST", "") or ""),
                    public_ip=None,
                    stream_ip=str(getattr(settings, "STREAM_PUBLIC_HOST", "") or "") or None,
                    http_port=int(getattr(settings, "MEDIA_SERVER_HTTP_PORT", 80) or 80),
                    https_port=0,
                    rtsp_port=int(getattr(settings, "MEDIA_SERVER_RTSP_PORT", 554) or 554),
                    rtsps_port=0,
                    rtmp_port=int(getattr(settings, "MEDIA_SERVER_RTMP_PORT", 1935) or 1935),
                    rtmps_port=0,
                    rtp_proxy_port=int(getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT", 10000) or 10000),
                    rtp_port_mode="range" if "-" in str(getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT_RANGE", "") or "") else "single",
                    rtp_port_range_start=int(str(getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT_RANGE", "0-0")).split("-")[0] or 0),
                    rtp_port_range_end=int(str(getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT_RANGE", "0-0")).split("-")[-1] or 0),
                    secret=str(getattr(settings, "MEDIA_SERVER_SECRET", "") or ""),
                    hook_base_url=hook_base,
                    is_online=False,
                    load=0.0,
                    is_embedded=True,
                    auto_config_enabled=True,
                )
                session.add(embedded)
                await session.commit()
                logger.info("Default embedded media node created.")
        except Exception as e:
            logger.warning(f"Seed embedded media node failed: {e}")


async def reset_admin_password(new_password: str):
    """重置 admin 密码并解锁账户。"""
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.username == "admin")
        result = await session.execute(stmt)
        user = result.scalars().first()
        if not user:
            logger.error("Admin user does not exist. Run init_db first.")
            return
        user.hashed_password = security.get_password_hash(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.is_active = True
        user.is_superuser = True
        user.role = "owner"
        user.tenant_id = user.tenant_id or "default"
        await session.commit()
        # removed password fingerprint from logs to prevent offline brute-force
        logger.warning("=" * 60)
        logger.warning("Admin password has been RESET.")
        logger.warning("Account lock has been CLEARED.")
        logger.warning("Please change it immediately after first login!")
        logger.warning("=" * 60)


def _parse_password_from_args():
    # removed CLI password parsing to prevent exposure in process list
    return os.environ.get("ADMIN_INITIAL_PASSWORD", "").strip()


if __name__ == "__main__":
    _pwd = _parse_password_from_args()
    if _pwd:
        asyncio.run(reset_admin_password(_pwd))
    else:
        asyncio.run(init_db())
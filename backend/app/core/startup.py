"""
Startup phase orchestrator for PyGBSentry.

Extracts lifespan startup logic into testable, composable phase functions.
Each phase handles a specific initialization step with proper timeout and error handling.
"""
import asyncio
import random
from loguru import logger
from sqlalchemy import text

from app.core.config import settings
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务
from app.db.session import AsyncSessionLocal, engine


async def _session_call(fn):
    """Execute async fn(db) within an AsyncSession with timeout support."""
    async with AsyncSessionLocal() as db:
        if (getattr(engine.dialect, "name", None) or "").lower() == "sqlite":
            await db.execute(text(f"PRAGMA busy_timeout={settings.SQLITE_BUSY_TIMEOUT_MS}"))
        return await fn(db)


async def phase_schema_migration():
    """Phase 1: Run database schema migration (Alembic or legacy)."""
    use_alembic = getattr(settings, 'USE_ALEMBIC', False)
    if use_alembic:
        import subprocess
        import sys
        import os
        _backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        # FIXED-P0: 与 main.py 保持一致，使用 subprocess 调用 alembic CLI
        # 直接 import alembic 会与本地 alembic/ 目录产生命名冲突
        # 检测数据库是否已有表但无 alembic_version 记录（由 ensure_business_schema 创建）
        _need_stamp = False
        try:
            async with engine.connect() as conn:
                _dialect_name = (getattr(engine.dialect, "name", None) or "").lower()
                if _dialect_name == "sqlite":
                    _av_result = await conn.execute(text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
                    ))
                    if not _av_result.first():
                        _bt_result = await conn.execute(text(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('sqlite_sequence', '_alembic_tmp')"
                        ))
                        if _bt_result.fetchall():
                            _need_stamp = True
                elif _dialect_name == "postgresql":
                    # 检查 alembic_version 表是否存在且是否有版本记录
                    _av_result = await conn.execute(text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='alembic_version')"
                    ))
                    _av_exists = _av_result.scalar()
                    if not _av_exists:
                        # 无 alembic_version 表，检查是否有其他业务表
                        _bt_result = await conn.execute(text(
                            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name NOT IN ('alembic_version', '_alembic_tmp'))"
                        ))
                        if _bt_result.scalar():
                            _need_stamp = True
                    else:
                        # alembic_version 表存在但可能为空（之前部分运行）
                        _ver_result = await conn.execute(text(
                            "SELECT EXISTS (SELECT 1 FROM alembic_version)"
                        ))
                        if not _ver_result.scalar():
                            # 有表但无版本记录，检查是否有业务表
                            _bt_result = await conn.execute(text(
                                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name NOT IN ('alembic_version', '_alembic_tmp'))"
                            ))
                            if _bt_result.scalar():
                                _need_stamp = True
                elif _dialect_name == "mysql":
                    _av_result = await conn.execute(text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='alembic_version')"
                    ))
                    if not _av_result.scalar():
                        _bt_result = await conn.execute(text(
                            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name NOT IN ('alembic_version'))"
                        ))
                        if _bt_result.scalar():
                            _need_stamp = True
        except Exception as _stamp_check_err:
            logger.warning(f"alembic stamp pre-check error: {_stamp_check_err}")

        if _need_stamp:
            logger.info("Startup step: stamping alembic version (database has tables but no alembic_version)...")
            try:
                _stamp_result = subprocess.run(
                    [sys.executable, "-m", "alembic", "stamp", "head"],
                    cwd=_backend_dir,
                    capture_output=True, text=True, timeout=30,
                )
                if _stamp_result.returncode == 0:
                    logger.info("Startup step: alembic stamp head done.")
                else:
                    logger.warning(f"alembic stamp head failed: {_stamp_result.stderr[-300:]}")
            except Exception as _stamp_err:
                logger.warning(f"alembic stamp head error: {_stamp_err}")

        logger.info("Startup step: alembic upgrade head...")
        try:
            _result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=_backend_dir,
                capture_output=True, text=True, timeout=120,
            )
            if _result.returncode == 0:
                logger.info("Startup step: alembic upgrade head done.")
            else:
                _stderr = _result.stderr or ""
                logger.error(f"alembic upgrade head failed (exit {_result.returncode}): {_stderr[-500:]}")
                # FIXED-P0: upgrade 失败且错误是"表已存在"时，自动 stamp head
                _dup_keywords = ("already exists", "DuplicateTable", "DuplicateColumn", "DuplicateObject")
                if any(kw.lower() in _stderr.lower() for kw in _dup_keywords):
                    logger.warning("Detected 'already exists' error — stamping alembic to head and continuing...")
                    try:
                        _stamp_result = subprocess.run(
                            [sys.executable, "-m", "alembic", "stamp", "head"],
                            cwd=_backend_dir,
                            capture_output=True, text=True, timeout=30,
                        )
                        if _stamp_result.returncode == 0:
                            logger.info("Startup step: alembic stamp head done (after duplicate error).")
                        else:
                            logger.warning(f"alembic stamp head failed: {_stamp_result.stderr[-300:]}")
                    except Exception as _stamp_err:
                        logger.warning(f"alembic stamp head error: {_stamp_err}")
        except subprocess.TimeoutExpired:
            logger.error("alembic upgrade head timed out (120s)")
        except Exception as _alembic_err:
            logger.error(f"alembic upgrade head error: {_alembic_err}")

        # FIXED-P0: alembic stamp head 只标记版本号，不创建缺失的表
        # 用 Base.metadata.create_all 兜底补建所有缺失的表
        try:
            from app.db.model_registry import ensure_model_registry_loaded
            from app.db.base import Base
            ensure_model_registry_loaded()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Startup step: ensure all ORM tables exist (create_all fallback) done.")
        except Exception as _create_all_err:
            logger.warning(f"Startup step: create_all fallback error: {_create_all_err}")
    else:
        logger.info("Startup step: ensure_business_schema...")
        from app.services.schema_upgrade import ensure_business_schema
        await ensure_business_schema()
        logger.info("Startup step: ensure_business_schema done.")


async def phase_load_plugin_config(plugin_manager):
    """Phase 2: Load published plugin configuration from DB."""
    logger.info("Startup step: load_published_plugin_config...")
    try:
        from app.services.config_center_service import config_center_service

        async def _load_pub(db):
            return await config_center_service._load_published_modules(db)

        published = await asyncio.wait_for(_session_call(_load_pub), timeout=30)
        _revision, published_data = published
        plugin_manager._runtime_plugin_config = published_data.get("plugins") or {}
        logger.info("Startup step: load_published_plugin_config done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: load_published_plugin_config timeout (30s), using defaults")
        plugin_manager._runtime_plugin_config = {}
    except Exception as e:
        logger.warning("Load published plugin config failed: %s, using defaults" % e)
        plugin_manager._runtime_plugin_config = {}


async def phase_load_plugins(plugin_manager):
    """Phase 3: Load and start plugins."""
    logger.info("Startup step: plugin_manager.load_plugins...")
    plugin_manager.load_plugins()
    logger.info("Startup step: plugin_manager.load_plugins done.")

    import app as app_pkg
    app_pkg.services.notify_manager.init_notify_manager()

    from app.core.plugin_manager import HOOK_ON_STARTUP
    logger.info("Startup step: plugin_manager.emit(HOOK_ON_STARTUP)...")
    try:
        await asyncio.wait_for(plugin_manager.emit(HOOK_ON_STARTUP), timeout=20)
        logger.info("Startup step: plugin_manager.emit(HOOK_ON_STARTUP) done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: plugin_manager.emit(HOOK_ON_STARTUP) timeout (20s), continue startup.")
    except Exception as e:
        logger.warning(f"Startup step: plugin_manager.emit(HOOK_ON_STARTUP) failed: {e}, continue startup.")

    # Plugin health check loop
    try:
        await plugin_manager.start_health_check_loop()
        logger.info("Startup step: plugin health check loop started.")
    except Exception as e:
        logger.warning(f"Startup step: plugin health check loop failed: {e}, continue startup.")


async def phase_marketplace_registration(plugin_manager):
    """Phase 4: Register OSS instance to marketplace (if enabled)."""
    if not bool(getattr(settings, "PLUGIN_MARKETPLACE_ENABLED", False)):
        logger.info("Startup step: PLUGIN_MARKETPLACE_ENABLED=False, marketplace integration disabled.")
        return

    try:
        from app.services.license_service import _get_current_machine_code
        _machine_code = _get_current_machine_code()
        await plugin_manager.register_oss_instance(machine_code=_machine_code)
        logger.info("Startup step: OSS instance registered to marketplace server.")
    except Exception as e:
        logger.warning(f"Startup step: OSS instance register failed: {e}, continue startup.")

    # License refresh subscriber
    try:
        fire_and_forget(plugin_manager.start_license_refresh_subscriber())  # P0-16: 保存引用防 GC + 异常日志
        logger.info("Startup step: license refresh Redis subscriber started.")
    except Exception as e:
        logger.warning(f"Startup step: license refresh subscriber failed: {e}, continue startup.")


async def phase_data_migrations():
    """Phase 5: Run optional data migrations (split catalog, regions, embedded media node)."""
    # Split catalog migrations
    if not bool(getattr(settings, "RUN_SPLIT_CATALOG_MIGRATIONS_ON_STARTUP", False)):
        logger.info(
            "Startup step: split_migrations skipped (RUN_SPLIT_CATALOG_MIGRATIONS_ON_STARTUP=false). "
            "To migrate an old database, set to true in .env or run: python scripts/run_split_catalog_migrations.py"
        )
    else:
        logger.info("Startup step: split_migrations...")
        _dialect = (getattr(engine.dialect, "name", None) or "").lower()
        try:
            from app.services.channel_placement_migration import ensure_split_channel_region_parents
            from app.services.region_directory_split_migration import ensure_split_region_directory_parents

            resource_rows = 0

            async def _count_resources_rows() -> int:
                async with engine.connect() as conn:
                    if _dialect == "sqlite":
                        await conn.execute(text(f"PRAGMA busy_timeout={settings.SQLITE_BUSY_TIMEOUT_MS}"))
                    cnt_res = await conn.execute(text("SELECT COUNT(1) FROM resources"))
                    return int(cnt_res.scalar() or 0)

            logger.info("Startup step: split_migrations counting resources (raw connection)...")
            try:
                resource_rows = await asyncio.wait_for(_count_resources_rows(), timeout=25.0)
            except asyncio.TimeoutError:
                logger.error(
                    "Startup step: split_migrations COUNT timeout (25s). "
                    "Please check if another process is using pygbsentry.db (lsof ./pygbsentry.db), "
                    "or increase SQLITE_CONNECT_TIMEOUT_SECONDS in .env."
                )
                resource_rows = -1
            except Exception as e:
                logger.warning("Startup step: split_migrations COUNT resources failed (skip migrations): {}", e)
                resource_rows = -1
            logger.info("Startup step: split_migrations count result: {}", resource_rows)

            if resource_rows == 0:
                logger.info("Startup step: split_migrations skipped (resources table empty, nothing to migrate)")
            elif resource_rows < 0:
                logger.warning("Startup step: split_migrations skipped (could not count resources)")
            else:
                logger.info("Startup step: split_migrations running (resources rows={})...", resource_rows)
                async with AsyncSessionLocal() as db:
                    logger.info("Startup step: ensure_split_channel_region_parents...")
                    n = await asyncio.wait_for(ensure_split_channel_region_parents(db), timeout=60)
                    if n:
                        logger.info("Startup step: channel placement split migration => {}", n)
                    logger.info("Startup step: ensure_split_channel_region_parents done.")
                    logger.info("Startup step: ensure_split_region_directory_parents...")
                    d = await asyncio.wait_for(ensure_split_region_directory_parents(db), timeout=60)
                    if d:
                        logger.info("Startup step: directory split migration => {}", d)
                    logger.info("Startup step: ensure_split_region_directory_parents done.")
            logger.info("Startup step: split_migrations done.")
        except asyncio.TimeoutError:
            logger.warning("Startup step: split_migrations timeout, continue startup.")
        except Exception as e:
            logger.warning("Channel placement split migration skipped/failed: {}", e)

    # Region seeding
    if not bool(getattr(settings, "RUN_REGION_SEED_ON_STARTUP", False)):
        logger.info(
            "Startup step: ensure_regions_seeded_from_sql skipped (RUN_REGION_SEED_ON_STARTUP=false). "
            "To use built-in regions, set to true in .env or run: python scripts/seed_regions.py"
        )
    else:
        logger.info("Startup step: ensure_regions_seeded_from_sql...")
        try:
            from app.services.region_import_service import ensure_regions_seeded_from_sql
            seeded = await asyncio.wait_for(_session_call(ensure_regions_seeded_from_sql), timeout=120)
            logger.info("Startup step: ensure_regions_seeded_from_sql => {}", seeded)
            logger.info("Startup step: ensure_regions_seeded_from_sql done.")
        except asyncio.TimeoutError:
            logger.warning("Startup step: ensure_regions_seeded_from_sql timeout (120s), continue startup.")
        except Exception as e:
            logger.warning(f"Startup step: ensure_regions_seeded_from_sql failed: {e}")

    # Embedded media node
    if not bool(getattr(settings, "ENSURE_EMBEDDED_MEDIA_NODE_ON_STARTUP", False)):
        logger.info(
            "Startup step: ensure_embedded_media_node skipped (ENSURE_EMBEDDED_MEDIA_NODE_ON_STARTUP=false). "
            "If initial_data has not been run or node needs to be populated: python scripts/ensure_embedded_media_node.py"
        )
    else:
        logger.info("Startup step: ensure_embedded_media_node...")
        try:
            from app.core.media_nodes_db import ensure_embedded_media_node
            embedded_id = await asyncio.wait_for(_session_call(ensure_embedded_media_node), timeout=30)
            if embedded_id:
                logger.info(f"Startup step: ensure_embedded_media_node ok (id={embedded_id}).")
            logger.info("Startup step: ensure_embedded_media_node done.")
        except asyncio.TimeoutError:
            logger.warning(
                "Startup step: ensure_embedded_media_node timeout (30s), continue startup. "
                "If this occurs frequently, check: lsof ./pygbsentry.db for multiple processes using the database"
            )
        except Exception as e:
            logger.warning(f"Startup step: ensure_embedded_media_node failed: {e}")


async def phase_init_sip_state_backend():
    """Phase 6: Initialize SIP state backend."""
    try:
        from app.sip.state_backend import get_sip_state_backend as _get_sip_state_backend
        _backend = _get_sip_state_backend()
        _backend_type = type(_backend).__name__
        logger.info(f"Startup step: SipStateBackend initialized (type={_backend_type})")
    except Exception as e:
        logger.error(f"Startup step: SipStateBackend init failed: {e}, continue startup.")


async def phase_check_secret_consistency():
    """Phase 7: Verify MEDIA_SERVER_SECRET consistency with DB."""
    # P0-02: secret 列已加密存储，需通过 decrypted_secret 取明文后比较
    try:
        async def _check_secret_consistency(db):
            from app.models.media_node import MediaNode as _MN
            from sqlalchemy import select as _sel
            result = await db.execute(_sel(_MN).where(_MN.is_embedded).limit(1))
            return result.scalars().first()

        _secret_node = await asyncio.wait_for(_session_call(_check_secret_consistency), timeout=10)
        if _secret_node:
            _db_secret_plain = _secret_node.decrypted_secret
            if _db_secret_plain and _db_secret_plain != settings.MEDIA_SERVER_SECRET:
                _app_env = (getattr(settings, "APP_ENV", "dev") or "dev").lower()
                if _app_env in {"prod", "production"}:
                    logger.error(
                        "FATAL: MEDIA_SERVER_SECRET mismatch with DB MediaNode.secret (node_id=%s). "
                        "ZLM API calls will FAIL. Please ensure MEDIA_SERVER_SECRET in .env matches the secret in DB media_nodes table, "
                        "or run 'python scripts/update_media_node_secret.py' to sync DB with .env.",
                        _secret_node.id,
                    )
                    raise RuntimeError(
                        "MEDIA_SERVER_SECRET mismatch between .env and DB MediaNode.secret (node_id=%s). "
                        "ZLM API calls will fail. Please fix and restart." % _secret_node.id
                    )
                else:
                    logger.warning(
                        "MEDIA_SERVER_SECRET mismatch with DB MediaNode.secret (node_id=%s). "
                        "ZLM API calls may fail. This is acceptable in dev, but please ensure they match.",
                        _secret_node.id,
                    )
    except asyncio.TimeoutError:
        logger.warning("Startup step: secret consistency check timeout (10s), skipped.")
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("Startup step: secret consistency check skipped: %s", e)


async def phase_init_redis():
    """Phase 8: Initialize Redis connection."""
    if not bool(getattr(settings, "INIT_REDIS_ON_STARTUP", False)):
        logger.info(
            "Startup step: init_redis skipped (INIT_REDIS_ON_STARTUP=false). "
            "Set INIT_REDIS_ON_STARTUP=true in .env and start redis-server when Redis is needed"
        )
        return

    logger.info("Startup step: init_redis...")
    try:
        from app.core.redis import init_redis
        redis_task = asyncio.create_task(init_redis())
        done, pending = await asyncio.wait({redis_task}, timeout=10)
        if redis_task in done:
            exc = redis_task.exception()
            if exc:
                raise exc
            logger.info("Startup step: init_redis done.")
        else:
            for t in pending:
                t.cancel()
            logger.warning("Startup step: init_redis timeout (10s). Continue startup without Redis.")
    except Exception as e:
        logger.error(f"Startup step: init_redis failed: {e}. Continue startup without Redis.")


async def phase_init_sip(sip_server):
    """Phase 9: Initialize SIP handlers and start SIP server."""
    from app.sip.handlers import init_handlers
    from app.sip.commander import SipCommander
    from app.sip.invite import SipInvite
    from app.sip.ptz import SipPtz
    from app.sip.record import SipRecord
    from app.sip.talk import SipTalk
    from app.sip.playback_control import PlaybackControl
    from app.sip.device_control import DeviceControl
    from app.sip.catalog import Catalog
    import app as app_pkg

    logger.info("Startup step: init_handlers...")
    init_handlers()
    logger.info("Startup step: init_handlers done.")

    # Init Commanders
    app_pkg.sip.commander.sip_commander = SipCommander(sip_server)
    app_pkg.sip.invite.sip_invite = SipInvite(sip_server)
    app_pkg.sip.ptz.sip_ptz = SipPtz(sip_server)
    app_pkg.sip.record.sip_record = SipRecord(sip_server)
    app_pkg.sip.talk.sip_talk = SipTalk(sip_server)
    app_pkg.sip.playback_control.playback_control = PlaybackControl(sip_server)
    app_pkg.sip.device_control.device_control = DeviceControl(sip_server)
    app_pkg.sip.catalog.catalog = Catalog(sip_server)

    logger.info("Startup step: sip_server.start...")
    try:
        await asyncio.wait_for(sip_server.start(), timeout=20)
        logger.info("Startup step: sip_server.start done.")
    except asyncio.TimeoutError:
        if bool(getattr(settings, "SIP_STARTUP_REQUIRED", True)):
            logger.error("Startup step: sip_server.start timeout (20s), abort startup.")
            raise
        logger.warning("Startup step: sip_server.start timeout (20s), continue startup without SIP.")
    except OSError as e:
        if bool(getattr(settings, "SIP_STARTUP_REQUIRED", True)):
            logger.error(f"Startup step: sip_server.start failed: {e}. abort startup.")
            raise
        logger.warning(f"Startup step: sip_server.start failed: {e}. Continue startup without SIP.")


async def phase_init_platform_service(sip_server):
    """Phase 10: Start platform service (cascade) and subscriptions."""
    import app as app_pkg
    from app.services.platform_service import PlatformService

    app_pkg.services.platform_service.platform_service = PlatformService(sip_server)
    if not sip_server.running:
        logger.warning("Startup step: platform_service.start skipped (SIP not running).")
    else:
        logger.info("Startup step: platform_service.start...")
        try:
            await asyncio.wait_for(app_pkg.services.platform_service.platform_service.start(), timeout=20)
            logger.info("Startup step: platform_service.start done.")
        except asyncio.TimeoutError:
            logger.warning("Startup step: platform_service.start timeout (20s), continue startup.")

    # Cluster Pub/Sub subscriber
    try:
        from app.core.redis import ha_cluster
        await ha_cluster.start_subscriber()
        logger.info("Startup step: cluster subscriber started.")
    except Exception as e:
        logger.warning(f"Startup step: cluster subscriber start failed (non-critical): {e}")

    # Platform subscription service
    logger.info("Startup step: platform_subscription_service.start...")
    try:
        from app.services.platform_subscription_service import platform_subscription_service
        await asyncio.wait_for(platform_subscription_service.start(), timeout=10)
        logger.info("Startup step: platform_subscription_service.start done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: platform_subscription_service.start timeout (10s), continue startup.")
    except Exception as e:
        logger.warning(f"Startup step: platform_subscription_service.start failed: {e}, continue startup.")

    # Device subscription service
    logger.info("Startup step: device_subscription_service.start...")
    try:
        from app.services.device_subscription_service import device_subscription_service
        await asyncio.wait_for(device_subscription_service.start(), timeout=10)
        logger.info("Startup step: device_subscription_service.start done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: device_subscription_service.start timeout (10s), continue startup.")


async def phase_start_background_services(sip_server, plugin_manager):
    """Phase 11: Start catalog prune, AI vision, ZLM, health, and background tasks."""
    import app as app_pkg

    # Catalog aggregation prune
    try:
        from app.sip.catalog import start_catalog_agg_prune
        start_catalog_agg_prune()
    except Exception as e:
        logger.warning(f"Startup step: catalog_agg_prune start failed (non-critical): {e}")

    # AI Vision Hub
    from app.services.vision_hub import VisionHub
    app_pkg.services.vision_hub.vision_hub = VisionHub()
    logger.info("Startup step: vision_hub.start...")
    try:
        await asyncio.wait_for(app_pkg.services.vision_hub.vision_hub.start(), timeout=20)
        logger.info("Startup step: vision_hub.start done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: vision_hub.start timeout (20s), continue startup.")

    # Embedded ZLMediaKit
    from app.services.media_manager import media_manager
    zlm_boot_timeout = int(getattr(settings, "EMBEDDED_ZLM_START_TIMEOUT_SECONDS", 3600) or 0)
    logger.info("Startup step: media_manager.start (embedded ZLM)...")
    try:
        if zlm_boot_timeout > 0:
            await asyncio.wait_for(media_manager.start(), timeout=float(zlm_boot_timeout))
        else:
            await media_manager.start()
        logger.info("Startup step: media_manager.start done.")
    except asyncio.TimeoutError:
        logger.error(
            "Startup step: media_manager.start timeout ({}s), continue startup without embedded ZLM. "
            "If building ZLM from source, raise EMBEDDED_ZLM_START_TIMEOUT_SECONDS in .env or use a prebuilt MediaServer.",
            zlm_boot_timeout,
        )
    except Exception as e:
        logger.error(f"Startup step: media_manager.start failed: {e}")

    # Health Service
    from app.services.health_service import health_service
    logger.info("Startup step: health_service.start...")
    try:
        await asyncio.wait_for(health_service.start(), timeout=20)
        logger.info("Startup step: health_service.start done.")
    except asyncio.TimeoutError:
        logger.warning("Startup step: health_service.start timeout (20s), continue startup.")

    # Background tasks
    from app.services.tasks.task_manager import start_all_background_tasks
    await start_all_background_tasks(plugin_manager=plugin_manager)

    # SSL certbot
    try:
        from app.services.ssl_certbot.certbot_manager import on_startup
        await asyncio.wait_for(on_startup(), timeout=130)
    except asyncio.TimeoutError:
        logger.warning("SSL certbot startup check timeout (130s), continuing startup.")
    except Exception as e:
        logger.warning(f"SSL certbot startup check error (non-fatal): {e}")


async def phase_start_license_sync(plugin_manager):
    """Phase 12: Start paid license sync loop and OSS heartbeat."""
    paid_license_sync_task = None
    sync_enabled = bool(getattr(settings, "PLUGIN_PAID_LICENSE_SYNC_ENABLED", True))
    try:
        configured_interval = int(getattr(settings, "PLUGIN_PAID_LICENSE_SYNC_INTERVAL_SECONDS", 0) or 0)
    except Exception:
        configured_interval = 0
    try:
        fallback_interval = int(getattr(settings, "PLUGIN_PAID_HOOK_LICENSE_RECHECK_SECONDS", 60) or 0)
    except Exception:
        fallback_interval = 0
    paid_license_sync_interval = configured_interval if configured_interval > 0 else fallback_interval
    if bool(getattr(settings, "PLUGIN_LICENSE_DAILY_CHECK_MODE", False)):
        daily_interval = 86400
        if paid_license_sync_interval > 0:
            paid_license_sync_interval = max(paid_license_sync_interval, daily_interval)
        else:
            paid_license_sync_interval = daily_interval
    try:
        paid_license_sync_jitter = max(0, int(getattr(settings, "PLUGIN_PAID_LICENSE_SYNC_JITTER_SECONDS", 5) or 0))
    except Exception:
        paid_license_sync_jitter = 0
    run_sync_on_startup = bool(getattr(settings, "PLUGIN_PAID_LICENSE_SYNC_ON_STARTUP", True))

    if sync_enabled and paid_license_sync_interval > 0:
        async def _paid_license_sync_loop():
            if run_sync_on_startup:
                try:
                    cnt = plugin_manager.recheck_paid_plugins_licenses_now()
                    logger.info("Paid license sync (startup) finished: checked {} plugin(s)", cnt)
                except Exception as e:
                    logger.warning("Paid license sync (startup) failed: {}", e)
            while True:
                sleep_seconds = paid_license_sync_interval
                if paid_license_sync_jitter > 0:
                    sleep_seconds = max(1, paid_license_sync_interval + random.randint(-paid_license_sync_jitter, paid_license_sync_jitter))
                await asyncio.sleep(sleep_seconds)
                try:
                    cnt = plugin_manager.recheck_paid_plugins_licenses_now()
                    logger.debug("Paid license sync tick: checked {} plugin(s)", cnt)
                except Exception as e:
                    logger.warning("Paid license sync tick failed: {}", e)

        paid_license_sync_task = asyncio.create_task(_paid_license_sync_loop())

    # OSS heartbeat
    oss_heartbeat_task = None
    oss_heartbeat_interval = 300
    try:
        oss_heartbeat_interval = max(60, int(getattr(settings, "OSS_INSTANCE_HEARTBEAT_INTERVAL_SECONDS", 300) or 300))
    except Exception as e:
        logger.warning(f"Failed to parse OSS heartbeat interval: {e}")
    if getattr(plugin_manager, "_oss_instance_id", None):
        async def _oss_heartbeat_loop():
            while True:
                await asyncio.sleep(oss_heartbeat_interval)
                try:
                    result = await plugin_manager.oss_instance_check_in()
                    if result.get("ok"):
                        logger.debug("OSS instance heartbeat ok")
                    else:
                        logger.warning("OSS instance heartbeat failed: {}", result.get("error"))
                except Exception as e:
                    logger.warning("OSS instance heartbeat error: {}", e)

        oss_heartbeat_task = asyncio.create_task(_oss_heartbeat_loop())

    return paid_license_sync_task, oss_heartbeat_task


async def phase_start_cleanup_loops():
    """Phase 13: Start dialog, SSRC, and catalog cleanup loops."""
    from app.sip.dialog_manager import dialog_manager
    from app.sip.ssrc_manager import ssrc_manager
    from app.sip.catalog_data_manager import catalog_data_manager

    _bg_dialog_cleanup = asyncio.create_task(dialog_manager.cleanup_loop())
    _bg_ssrc_cleanup = asyncio.create_task(ssrc_manager.cleanup_loop())
    _bg_catalog_monitor = asyncio.create_task(catalog_data_manager.monitor_loop())

    return _bg_dialog_cleanup, _bg_ssrc_cleanup, _bg_catalog_monitor


async def phase_start_log_drain():
    """Phase 14: Start log WebSocket queue consumer."""
    from app.api.v1.endpoints.logs import log_manager, _get_log_queue

    async def _drain_log_queue(manager, get_queue):
        while True:
            try:
                q = get_queue()
                log_entry = await asyncio.wait_for(q.get(), timeout=5.0)
                await manager.broadcast_log(log_entry)
            except asyncio.TimeoutError:
                continue
            except Exception:
                await asyncio.sleep(1)

    _log_drain_task = asyncio.create_task(_drain_log_queue(log_manager, _get_log_queue))
    logger.info("Startup step: log queue drainer started.")
    return _log_drain_task


def emit_security_warnings():
    """Emit security warnings for non-ideal configurations."""
    _security_warnings = []
    if not getattr(settings, "PLUGIN_LICENSE_MACHINE_CODE_ENABLED", False):
        _security_warnings.append("PLUGIN_LICENSE_MACHINE_CODE_ENABLED=False: machine code binding disabled, license can be copied across machines")
    if not getattr(settings, "PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED", False):
        _security_warnings.append("PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED=False: activation token disabled, trial period can be reset")
    if not getattr(settings, "PLUGIN_PACKAGE_INTEGRITY_REQUIRED_IN_PROD", False):
        _security_warnings.append("PLUGIN_PACKAGE_INTEGRITY_REQUIRED_IN_PROD=False: package signature verification disabled, plugin packages can be tampered")
    if _security_warnings and (getattr(settings, "APP_ENV", "dev") or "dev").lower() in {"prod", "production"}:
        for _w in _security_warnings:
            logger.warning(f"[Security] {_w}")
        logger.warning("[Security] The above anti-piracy layers are disabled by default. Enable them in .env for production. See BUSINESS_MODEL_FIXES.md FIX-02")
